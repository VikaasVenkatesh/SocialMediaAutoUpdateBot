"""
Phase 1b — Trend signals (free, compliant).

Google Trends via pytrends (no auth, free) pulls rising/top related queries for
the niche scoped to California — a genuine "what's trending in this niche" signal
that complements the YouTube collector. Stored in the `trends` table and shown on
the dashboard. Other sources (Reddit, Instagram Hashtag Search) are documented as
optional adapters that need credentials.

Standalone debug:  python -m trends [run_id]
"""

import datetime as dt
import time

import config
import db

# Broad, higher-volume seed terms (hyper-specific town queries return empty).
TREND_SEED_TERMS = ["homes for sale", "housing market", "real estate"]
TREND_GEO = "US-CA"           # California
TREND_TIMEFRAME = "today 3-m"
TREND_MAX_PER_KIND = 10       # keep it tidy


def collect_google_trends(run_id: str) -> int:
    """Pull rising + top related queries for the seed terms. Returns row count."""
    try:
        from pytrends.request import TrendReq
    except ImportError:
        print("[1b] pytrends not installed — skipping Google Trends.")
        return 0

    pytrends = TrendReq(hl="en-US", tz=480)
    now = dt.datetime.now().isoformat(timespec="seconds")
    rows = []

    for term in TREND_SEED_TERMS:
        try:
            pytrends.build_payload([term], geo=TREND_GEO, timeframe=TREND_TIMEFRAME)
            related = pytrends.related_queries().get(term, {})
        except Exception as e:
            print(f"[1b] Google Trends failed for '{term}': {str(e)[:120]}")
            continue
        for kind in ("rising", "top"):
            df = related.get(kind)
            if df is None:
                continue
            for rec in df.head(TREND_MAX_PER_KIND).to_dict("records"):
                rows.append({
                    "run_id": run_id, "collected_at": now,
                    "source": "google_trends", "seed_term": term, "kind": kind,
                    "query": str(rec.get("query", ""))[:200],
                    "value": int(rec.get("value", 0) or 0), "geo": TREND_GEO,
                })
        time.sleep(1)  # be gentle with the unofficial endpoint

    inserted = 0
    with db.get_conn() as conn:
        for r in rows:
            cur = conn.execute(
                "INSERT OR IGNORE INTO trends(run_id, collected_at, source, "
                "seed_term, kind, query, value, geo) VALUES "
                "(:run_id,:collected_at,:source,:seed_term,:kind,:query,:value,:geo)",
                r,
            )
            inserted += cur.rowcount
    print(f"[1b] Google Trends: {inserted} trending queries stored")
    return inserted


def collect(run_id: str) -> int:
    db.init_db()
    return collect_google_trends(run_id)


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else f"trends-{dt.date.today()}"
    db.init_db()
    with db.get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO runs(run_id, started_at) VALUES (?,?)",
                     (rid, dt.datetime.now().isoformat(timespec="seconds")))
    collect(rid)
