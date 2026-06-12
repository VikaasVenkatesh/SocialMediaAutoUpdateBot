"""
Phase 2 — Study.

1. Compute an engagement score per collected post for this run.
   - If views are known (YouTube): raw = (likes+comments+shares)/views.
   - Otherwise (seed CSV): raw = likes+comments+shares.
   Raw signals aren't comparable across platforms, so we convert each post's raw
   value into a *percentile rank within its own platform* (0..1). That is the
   engagement_score we store and rank on.
2. Take the top config.TOP_PERCENT_TO_STUDY by score.
3. Send those to Claude (Haiku, cheapest) in ONE batched call that returns a
   JSON array: per post -> hook type, format, caption structure/length, hashtag
   strategy, CTA style, topic category.
4. Aggregate into a single `pattern_reports` row (JSON + human summary) and log
   estimated token spend to the `runs` table.

Standalone debug:  python -m phases.p2_study [run_id]
"""

import datetime as dt
import json
import os

from dotenv import load_dotenv

import config
import db
from costs import estimate_cost, log_spend

load_dotenv()

# Fields we ask Claude to extract per post.
EXTRACT_FIELDS = [
    "hook_type",          # question | bold_claim | stat | story | listicle | ...
    "format",             # short | long | carousel | image | text
    "caption_structure",  # e.g. hook->proof->cta
    "caption_length",     # short | medium | long
    "hashtag_strategy",   # none | few_niche | many_broad | location_tags | ...
    "cta_style",          # dm_keyword | link | comment | soft | none
    "topic_category",     # market_update | listing_tour | tips | testimonial | ...
]


# ---------------------------------------------------------------------------
# Step 1 — engagement scoring.
# ---------------------------------------------------------------------------
def _percentile_ranks(values):
    """Map each value to its percentile rank in [0,1] (ties share the rank)."""
    if not values:
        return []
    order = sorted(values)
    n = len(order)
    if n == 1:
        return [1.0]
    ranks = []
    for v in values:
        # fraction of values strictly less than v
        less = sum(1 for x in order if x < v)
        ranks.append(less / (n - 1))
    return ranks


def score_run(run_id: str) -> int:
    """Compute and persist engagement_score for every post in the run."""
    with db.get_conn() as conn:
        rows = conn.execute(
            "SELECT id, platform, likes, comments, shares, views "
            "FROM posts WHERE run_id = ?",
            (run_id,),
        ).fetchall()

        # group raw signals by platform
        by_platform = {}
        for r in rows:
            engagement = (r["likes"] or 0) + (r["comments"] or 0) + (r["shares"] or 0)
            raw = engagement / r["views"] if r["views"] else float(engagement)
            by_platform.setdefault(r["platform"], []).append((r["id"], raw))

        for platform, items in by_platform.items():
            ids = [i for i, _ in items]
            raws = [x for _, x in items]
            for pid, score in zip(ids, _percentile_ranks(raws)):
                conn.execute(
                    "UPDATE posts SET engagement_score = ? WHERE id = ?",
                    (round(score, 4), pid),
                )
    return len(rows)


def _top_posts(run_id: str):
    with db.get_conn() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM posts WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        if total == 0:
            return []
        k = max(1, round(total * config.TOP_PERCENT_TO_STUDY))
        rows = conn.execute(
            "SELECT id, platform, post_url, author, format, caption_text, "
            "likes, comments, shares, views, engagement_score "
            "FROM posts WHERE run_id = ? "
            "ORDER BY engagement_score DESC, (likes+comments+shares) DESC "
            "LIMIT ?",
            (run_id, k),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Step 3 — Claude (Haiku) extraction, one batched call.
# ---------------------------------------------------------------------------
def _extract_patterns(top_posts):
    """Return (per_post_list, usage_dict). Falls back to heuristics w/o a key."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("your-"):
        print("[p2] ANTHROPIC_API_KEY not set — using heuristic fallback.")
        return _heuristic_patterns(top_posts), {"input_tokens": 0, "output_tokens": 0}

    try:
        import anthropic
    except ImportError:
        print("[p2] anthropic lib missing — using heuristic fallback.")
        return _heuristic_patterns(top_posts), {"input_tokens": 0, "output_tokens": 0}

    client = anthropic.Anthropic(api_key=api_key)

    # Batch in chunks so the JSON response never overflows max_tokens (which
    # silently truncates and breaks parsing). ~20 posts/call is comfortable.
    chunk_size = 20
    all_parsed = []
    total_in = total_out = 0

    for start in range(0, len(top_posts), chunk_size):
        chunk = top_posts[start : start + chunk_size]
        payload = [
            {
                "i": idx,
                "platform": p["platform"],
                "format": p["format"],
                "caption": (p["caption_text"] or "")[:800],
            }
            for idx, p in enumerate(chunk)
        ]
        prompt = (
            "You are analyzing top-performing real estate social posts to extract "
            "reusable patterns. For EACH post in the JSON array, return an object "
            f"with exactly these keys: {EXTRACT_FIELDS}. Use short lowercase tokens. "
            "Return ONLY a JSON array, one object per input post, same order.\n\n"
            f"POSTS:\n{json.dumps(payload, ensure_ascii=False)}"
        )
        msg = client.messages.create(
            model=config.ANALYSIS_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        all_parsed.extend(_safe_json_array(text, expected=len(chunk)))
        total_in += msg.usage.input_tokens
        total_out += msg.usage.output_tokens

    return all_parsed, {"input_tokens": total_in, "output_tokens": total_out}


def _safe_json_array(text, expected):
    """Best-effort parse of a JSON array from model text."""
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1:
        try:
            arr = json.loads(text[start : end + 1])
            if isinstance(arr, list):
                return arr
        except json.JSONDecodeError:
            pass
    print("[p2] could not parse Claude JSON — returning empty extraction.")
    return [{} for _ in range(expected)]


def _heuristic_patterns(top_posts):
    """Cheap no-API extraction so the pipeline runs end-to-end without a key."""
    out = []
    for p in top_posts:
        cap = (p["caption_text"] or "")
        low = cap.lower()
        out.append(
            {
                "hook_type": "question" if "?" in cap.split("\n")[0] else "statement",
                "format": p["format"],
                "caption_structure": "hook->body->cta",
                "caption_length": "short" if len(cap) < 150 else
                                  "long" if len(cap) > 400 else "medium",
                "hashtag_strategy": "few_niche" if "#" in cap else "none",
                "cta_style": "dm_keyword" if " dm " in f" {low} " else
                             "link" if "http" in low else
                             "comment" if "comment" in low else "soft",
                "topic_category": "market_update" if "market" in low else
                                  "listing_tour" if any(w in low for w in
                                      ("tour", "for sale", "just listed")) else
                                  "testimonial" if "sold" in low else "tips",
            }
        )
    return out


# ---------------------------------------------------------------------------
# Step 4 — aggregate + persist.
# ---------------------------------------------------------------------------
def _aggregate(per_post):
    """Tally the dominant value for each field across the studied posts."""
    agg = {}
    for field in EXTRACT_FIELDS:
        counts = {}
        for obj in per_post:
            val = (obj or {}).get(field)
            if val:
                counts[str(val)] = counts.get(str(val), 0) + 1
        agg[field] = {
            "distribution": dict(sorted(counts.items(), key=lambda x: -x[1])),
            "dominant": max(counts, key=counts.get) if counts else None,
        }
    return agg


def _summarize(agg, studied):
    lines = [f"Studied {studied} top post(s). Dominant patterns:"]
    for field in EXTRACT_FIELDS:
        dom = agg[field]["dominant"]
        if dom:
            lines.append(f"- {field}: {dom}")
    return "\n".join(lines)


def study(run_id: str) -> int:
    """Score, study top ~20%, store a pattern report, return its row id."""
    db.init_db()
    scored = score_run(run_id)
    top = _top_posts(run_id)
    if not top:
        print("[p2] no posts to study.")
        return -1

    per_post, usage = _extract_patterns(top)
    agg = _aggregate(per_post)
    summary = _summarize(agg, len(top))

    report_json = json.dumps(
        {
            "patterns": agg,
            "per_post": per_post,
            "studied_post_ids": [p["id"] for p in top],
        },
        ensure_ascii=False,
    )

    with db.get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pattern_reports(run_id, created_at, posts_studied, "
            "report_json, summary) VALUES (?,?,?,?,?)",
            (run_id, dt.datetime.now().isoformat(timespec="seconds"),
             len(top), report_json, summary),
        )
        report_id = cur.lastrowid

    cost = estimate_cost(config.ANALYSIS_MODEL, usage["input_tokens"],
                         usage["output_tokens"])
    log_spend(run_id, usage["input_tokens"], usage["output_tokens"], cost)

    print(f"[p2] scored {scored} posts; studied {len(top)}; "
          f"report #{report_id}; est ${cost:.4f}")
    print(summary)
    return report_id


if __name__ == "__main__":
    import sys

    rid = sys.argv[1] if len(sys.argv) > 1 else f"debug-{dt.date.today()}"
    study(rid)
