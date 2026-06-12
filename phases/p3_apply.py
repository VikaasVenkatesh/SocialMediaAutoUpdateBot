"""
Phase 3 — Apply.

For each listing in config.LISTINGS, call Claude (Sonnet — quality matters for
generation) with the run's pattern report + the listing + config.BRAND_BRIEF.
Return, per target platform: a hook, full caption, hashtag set, suggested
format, and a 3–5 line short-video outline. Store rows in `drafts` linked to the
pattern report.

Standalone debug:  python -m phases.p3_apply [run_id] [pattern_report_id]
"""

import datetime as dt
import json
import os

from dotenv import load_dotenv

import config
import db
from costs import estimate_cost, log_spend

load_dotenv()


def _load_pattern_report(run_id, pattern_report_id):
    with db.get_conn() as conn:
        if pattern_report_id:
            row = conn.execute(
                "SELECT id, report_json, summary FROM pattern_reports WHERE id = ?",
                (pattern_report_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, report_json, summary FROM pattern_reports "
                "WHERE run_id = ? ORDER BY id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
    return row


def _build_prompt(listing, patterns_summary, patterns_json):
    platforms = ", ".join(config.TARGET_PLATFORMS)
    return (
        "You are a real estate content writer drafting approval-ready social "
        "posts. Match the broker's voice EXACTLY.\n\n"
        f"BRAND VOICE (must match): {config.BRAND_BRIEF}\n\n"
        f"TARGET MARKET CONTEXT: {config.MARKET_LABEL}\n\n"
        "WHAT TOP-PERFORMING POSTS ARE DOING (apply these patterns, don't copy "
        f"them):\n{patterns_summary}\n\nFull pattern data:\n"
        f"{json.dumps(patterns_json, ensure_ascii=False)}\n\n"
        f"LISTING TO PROMOTE:\n{json.dumps(listing, ensure_ascii=False)}\n\n"
        "Use ONLY facts present in the listing — never invent amenities, schools, "
        "or numbers. If a detail isn't given, speak generally or omit it.\n\n"
        f"For EACH of these platforms [{platforms}], produce: hook, caption, "
        "hashtags (array), suggested_format, video_outline (3-5 short lines as an "
        "array). Sign captions as Sri where natural.\n\n"
        "Return ONLY a JSON object mapping each platform name to an object with "
        "keys: hook, caption, hashtags, suggested_format, video_outline."
    )


def _generate_for_listing(client, listing, summary, patterns_json):
    """One Sonnet call per listing -> dict[platform] -> draft. Returns (data, usage)."""
    prompt = _build_prompt(listing, summary, patterns_json)
    msg = client.messages.create(
        model=config.GENERATION_MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    data = _safe_json_object(text)
    usage = {
        "input_tokens": msg.usage.input_tokens,
        "output_tokens": msg.usage.output_tokens,
    }
    return data, usage


def _safe_json_object(text):
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            obj = json.loads(text[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    print("[p3] could not parse Sonnet JSON — skipping this listing.")
    return {}


def _store_drafts(run_id, report_id, listing, platform_map):
    now = dt.datetime.now().isoformat(timespec="seconds")
    written = 0
    with db.get_conn() as conn:
        for platform, d in platform_map.items():
            if not isinstance(d, dict):
                continue
            conn.execute(
                "INSERT INTO drafts(run_id, created_at, listing_address, platform,"
                " hook, caption, hashtags, suggested_format, video_outline,"
                " pattern_report_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id, now, listing["address"], platform,
                    d.get("hook", ""),
                    d.get("caption", ""),
                    _join(d.get("hashtags")),
                    d.get("suggested_format", ""),
                    _join(d.get("video_outline"), sep="\n"),
                    report_id,
                ),
            )
            written += 1
    return written


def _join(val, sep=" "):
    if isinstance(val, list):
        return sep.join(str(x) for x in val)
    return str(val or "")


def _build_single_prompt(listing, platform, summary, patterns_json):
    return (
        "You are a real estate content writer drafting ONE approval-ready social "
        "post. Match the broker's voice EXACTLY.\n\n"
        f"BRAND VOICE (must match): {config.BRAND_BRIEF}\n\n"
        f"TARGET MARKET CONTEXT: {config.MARKET_LABEL}\n\n"
        "WHAT TOP-PERFORMING POSTS ARE DOING (apply, don't copy):\n"
        f"{summary}\n\nFull pattern data:\n"
        f"{json.dumps(patterns_json, ensure_ascii=False)}\n\n"
        f"LISTING:\n{json.dumps(listing, ensure_ascii=False)}\n\n"
        "Use ONLY facts present in the listing — never invent amenities, schools, "
        "or numbers. Sign as Sri where natural.\n\n"
        f"Write ONE post specifically for {platform.upper()}. Return ONLY a JSON "
        "object with keys: hook, caption, hashtags (array), suggested_format, "
        "video_outline (3-5 short lines as an array)."
    )


def generate_one(listing_address: str, platform: str, pattern_report_id: int = None):
    """Generate + store a single draft on demand (used by the dashboard button).

    Returns (draft_dict, error_str). On success error_str is None.
    """
    db.init_db()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("your-"):
        return None, "ANTHROPIC_API_KEY not set — add it to .env to generate."
    try:
        import anthropic
    except ImportError:
        return None, "anthropic library not installed."

    listing = next(
        (l for l in config.LISTINGS if l["address"] == listing_address), None
    )
    if not listing:
        return None, f"Unknown listing: {listing_address}"

    # Use the most recent pattern report (any run) as the style guide.
    with db.get_conn() as conn:
        if pattern_report_id:
            report = conn.execute(
                "SELECT id, run_id, report_json, summary FROM pattern_reports "
                "WHERE id = ?", (pattern_report_id,)).fetchone()
        else:
            report = conn.execute(
                "SELECT id, run_id, report_json, summary FROM pattern_reports "
                "ORDER BY id DESC LIMIT 1").fetchone()
    if not report:
        return None, "No pattern report yet — run the pipeline (python main.py) first."

    summary = report["summary"] or ""
    patterns_json = json.loads(report["report_json"]).get("patterns", {})
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=config.GENERATION_MODEL,
        max_tokens=1500,
        messages=[{"role": "user",
                   "content": _build_single_prompt(listing, platform, summary,
                                                    patterns_json)}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    d = _safe_json_object(text)
    if not d:
        return None, "Could not parse model output. Try again."

    _store_drafts(report["run_id"], report["id"], listing, {platform: d})
    cost = estimate_cost(config.GENERATION_MODEL, msg.usage.input_tokens,
                         msg.usage.output_tokens)
    log_spend(report["run_id"], msg.usage.input_tokens, msg.usage.output_tokens, cost)

    return {
        "listing_address": listing_address,
        "platform": platform,
        "hook": d.get("hook", ""),
        "caption": d.get("caption", ""),
        "hashtags": _join(d.get("hashtags")),
        "suggested_format": d.get("suggested_format", ""),
        "video_outline": _join(d.get("video_outline"), sep="\n"),
        "est_cost": round(cost, 4),
    }, None


def apply(run_id: str, pattern_report_id: int = None) -> int:
    """Generate drafts for every listing/platform, return count written."""
    db.init_db()
    report = _load_pattern_report(run_id, pattern_report_id)
    if not report:
        print("[p3] no pattern report found — run Phase 2 first.")
        return 0
    report_id = report["id"]
    summary = report["summary"] or ""
    patterns_json = json.loads(report["report_json"]).get("patterns", {})

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key or api_key.startswith("your-"):
        print("[p3] ANTHROPIC_API_KEY not set — cannot generate drafts. "
              "Set the key in .env to run Phase 3 (generation needs Sonnet).")
        return 0
    try:
        import anthropic
    except ImportError:
        print("[p3] anthropic lib missing — cannot generate drafts.")
        return 0

    client = anthropic.Anthropic(api_key=api_key)
    total_written = 0
    for listing in config.LISTINGS:
        platform_map, usage = _generate_for_listing(
            client, listing, summary, patterns_json
        )
        written = _store_drafts(run_id, report_id, listing, platform_map)
        total_written += written
        cost = estimate_cost(config.GENERATION_MODEL, usage["input_tokens"],
                             usage["output_tokens"])
        log_spend(run_id, usage["input_tokens"], usage["output_tokens"], cost)
        print(f"[p3] {listing['address']}: {written} drafts, est ${cost:.4f}")

    print(f"[p3] generated {total_written} drafts across "
          f"{len(config.LISTINGS)} listing(s)")
    return total_written


if __name__ == "__main__":
    import sys

    rid = sys.argv[1] if len(sys.argv) > 1 else f"debug-{dt.date.today()}"
    rpt = int(sys.argv[2]) if len(sys.argv) > 2 else None
    apply(rid, rpt)
