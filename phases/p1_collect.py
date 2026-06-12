"""
Phase 1 — Collect.

Pulls YouTube video metadata via the free Data API v3 and loads the manual
`seed_posts.csv`, normalizing every row into the `posts` table. Caps the total
at config.MAX_POSTS_PER_RUN. Engagement scoring happens in Phase 2; this phase
just gathers and normalizes.

Standalone debug:  python -m phases.p1_collect [run_id]
"""

import csv
import datetime as dt
import os

from dotenv import load_dotenv

import config
import db

load_dotenv()

VALID_PLATFORMS = {"youtube", "instagram", "x", "linkedin"}


# ---------------------------------------------------------------------------
# Shared insert helper (dedupes within a run via the UNIQUE constraint).
# ---------------------------------------------------------------------------
def _insert_posts(conn, rows) -> int:
    """Insert normalized rows, ignoring duplicates. Returns count inserted."""
    inserted = 0
    for r in rows:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO posts
                (platform, post_url, author, posted_at, format, caption_text,
                 likes, comments, shares, views, source, run_id, collected_at)
            VALUES
                (:platform, :post_url, :author, :posted_at, :format, :caption_text,
                 :likes, :comments, :shares, :views, :source, :run_id, :collected_at)
            """,
            r,
        )
        inserted += cur.rowcount
    return inserted


# ---------------------------------------------------------------------------
# Source A — YouTube Data API v3 (free, fully automated).
# ---------------------------------------------------------------------------
def collect_youtube(run_id: str, remaining: int):
    """Search per market x term, fetch stats, return normalized rows.

    Returns [] (and logs a warning) if no API key or the client lib is missing,
    so the PoC still runs on the CSV alone.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key or api_key.startswith("your-"):
        print("[p1] YOUTUBE_API_KEY not set — skipping YouTube, CSV only.")
        return []
    try:
        from googleapiclient.discovery import build
    except ImportError:
        print("[p1] google-api-python-client not installed — skipping YouTube.")
        return []

    yt = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    now = dt.datetime.now().isoformat(timespec="seconds")
    # Recent content only — published within the last 90 days.
    published_after = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=90)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    video_ids = []          # preserve discovery order
    meta_by_id = {}         # id -> partial row (title/author/url/posted_at)

    for market in config.TARGET_MARKETS:
        for term in config.YT_SEARCH_TERMS:
            if len(video_ids) >= remaining:
                break
            try:
                resp = (
                    yt.search()
                    .list(
                        q=f"{term} {market}",
                        part="snippet",
                        type="video",
                        order="viewCount",
                        publishedAfter=published_after,
                        maxResults=config.YT_RESULTS_PER_MARKET,
                    )
                    .execute()
                )
            except Exception as e:  # quota/network — degrade gracefully
                print(f"[p1] YouTube search failed for '{term} {market}': {e}")
                continue

            for item in resp.get("items", []):
                vid = item["id"].get("videoId")
                if not vid or vid in meta_by_id:
                    continue
                sn = item["snippet"]
                meta_by_id[vid] = {
                    "platform": "youtube",
                    "post_url": f"https://www.youtube.com/watch?v={vid}",
                    "author": sn.get("channelTitle"),
                    "posted_at": sn.get("publishedAt"),
                    "format": "long",  # refined below using duration
                    "caption_text": (sn.get("title", "") + "\n\n"
                                     + sn.get("description", "")).strip(),
                    "likes": 0, "comments": 0, "shares": 0, "views": 0,
                    "source": "youtube_api", "run_id": run_id,
                    "collected_at": now,
                }
                video_ids.append(vid)

    if not video_ids:
        return []

    # Hydrate statistics + duration in batches of 50 (API max per call).
    rows = []
    for i in range(0, min(len(video_ids), remaining), 50):
        batch = video_ids[i : i + 50]
        try:
            stats = (
                yt.videos()
                .list(part="statistics,contentDetails", id=",".join(batch))
                .execute()
            )
        except Exception as e:
            print(f"[p1] YouTube stats fetch failed: {e}")
            continue
        for item in stats.get("items", []):
            row = meta_by_id.get(item["id"])
            if not row:
                continue
            st = item.get("statistics", {})
            row["views"] = int(st.get("viewCount", 0) or 0)
            row["likes"] = int(st.get("likeCount", 0) or 0)
            row["comments"] = int(st.get("commentCount", 0) or 0)
            dur = item.get("contentDetails", {}).get("duration", "")
            row["format"] = "short" if _is_short(dur) else "long"
            rows.append(row)

    return rows[:remaining]


def _is_short(iso_duration: str) -> bool:
    """True if an ISO-8601 duration (e.g. PT45S, PT1M) is <= 60s (a Short)."""
    import re

    m = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not m:
        return False
    minutes = int(m.group(1) or 0)
    seconds = int(m.group(2) or 0)
    return minutes * 60 + seconds <= 60


# ---------------------------------------------------------------------------
# Source B — manual seed CSV (X / Instagram / LinkedIn), free + compliant.
# ---------------------------------------------------------------------------
def collect_seed_csv(run_id: str, remaining: int):
    """Read seed_posts.csv into normalized rows. Skips dummy/blank rows."""
    path = config.SEED_CSV_PATH
    if not os.path.exists(path):
        print(f"[p1] {path} not found — skipping seed CSV.")
        return []

    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):  # row 1 is the header
            if len(rows) >= remaining:
                break
            platform = (raw.get("platform") or "").strip().lower()
            if platform not in VALID_PLATFORMS:
                print(f"[p1] CSV row {i}: bad platform '{platform}', skipped.")
                continue
            caption = (raw.get("caption_text") or "").strip()
            if not caption:
                continue
            rows.append(
                {
                    "platform": platform,
                    "post_url": (raw.get("post_url") or "").strip(),
                    "author": (raw.get("author") or "").strip(),
                    "posted_at": None,  # not collected in the seed format
                    "format": (raw.get("format") or "").strip().lower() or "text",
                    "caption_text": caption,
                    "likes": _to_int(raw.get("likes")),
                    "comments": _to_int(raw.get("comments")),
                    "shares": _to_int(raw.get("shares_or_saves")),
                    "views": 0,  # rarely public on these platforms
                    "source": "seed_csv",
                    "run_id": run_id,
                    "collected_at": now,
                }
            )
    return rows


def _to_int(val) -> int:
    try:
        return int(str(val).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Orchestrator.
# ---------------------------------------------------------------------------
def collect(run_id: str) -> int:
    """Collect from all free sources, write normalized rows, return count."""
    db.init_db()
    cap = config.MAX_POSTS_PER_RUN

    yt_rows = collect_youtube(run_id, remaining=cap)
    remaining = cap - len(yt_rows)
    csv_rows = collect_seed_csv(run_id, remaining=max(remaining, 0))

    with db.get_conn() as conn:
        inserted = _insert_posts(conn, yt_rows + csv_rows)
        conn.execute(
            "UPDATE runs SET posts_collected = ? WHERE run_id = ?",
            (inserted, run_id),
        )

    print(
        f"[p1] collected {inserted} posts "
        f"(youtube={len(yt_rows)}, seed_csv={len(csv_rows)}, cap={cap})"
    )
    return inserted


if __name__ == "__main__":
    import sys

    rid = sys.argv[1] if len(sys.argv) > 1 else f"debug-{dt.date.today()}"
    # Ensure a runs row exists for standalone debugging.
    db.init_db()
    with db.get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO runs(run_id, started_at) VALUES (?, ?)",
            (rid, dt.datetime.now().isoformat(timespec="seconds")),
        )
    collect(rid)
