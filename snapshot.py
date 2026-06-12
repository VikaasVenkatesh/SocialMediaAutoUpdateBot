"""
Snapshot layer shared by the live dashboard and the Vercel deployment.

`build()` reads the local SQLite DB and returns the full dashboard payload as a
plain dict. `write()` dumps it to data/snapshot.json so it can be committed and
served by a serverless (Vercel) function that has no access to the local DB.

This is what makes a $0 Vercel deploy possible: the pipeline runs locally and
writes SQLite; you export a snapshot and push it; the hosted dashboard renders
that snapshot. Re-export + push to update it.
"""

import json
import os

import config
import db

SNAPSHOT_PATH = os.path.join(os.path.dirname(__file__), "data", "snapshot.json")


def build() -> dict:
    """Read SQLite and return the complete dashboard payload."""
    with db.get_conn() as conn:
        runs = [dict(r) for r in conn.execute(
            "SELECT run_id, started_at, posts_collected, est_cost_usd, "
            "est_input_tokens, est_output_tokens FROM runs "
            "ORDER BY started_at ASC"
        ).fetchall()]

        n_runs = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        n_posts = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        n_drafts = conn.execute("SELECT COUNT(*) FROM drafts").fetchone()[0]
        spend = conn.execute(
            "SELECT COALESCE(SUM(est_cost_usd), 0) FROM runs"
        ).fetchone()[0]

        prow = conn.execute(
            "SELECT run_id, posts_studied, report_json, summary "
            "FROM pattern_reports ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if prow:
            patterns = {
                "run_id": prow["run_id"],
                "posts_studied": prow["posts_studied"],
                "summary": prow["summary"],
                "patterns": json.loads(prow["report_json"]).get("patterns", {}),
            }
        else:
            patterns = {"run_id": None, "posts_studied": 0,
                        "summary": "No pattern report yet.", "patterns": {}}

        latest_draft = conn.execute(
            "SELECT run_id FROM drafts ORDER BY id DESC LIMIT 1"
        ).fetchone()
        listings = {}
        draft_run = None
        if latest_draft:
            draft_run = latest_draft["run_id"]
            for r in conn.execute(
                "SELECT listing_address, platform, hook, caption, hashtags, "
                "suggested_format, video_outline FROM drafts WHERE run_id = ? "
                "ORDER BY listing_address, platform", (draft_run,)
            ).fetchall():
                listings.setdefault(r["listing_address"], []).append(dict(r))

        # Latest trend signals (most recent run that has any).
        trow = conn.execute(
            "SELECT run_id FROM trends ORDER BY id DESC LIMIT 1"
        ).fetchone()
        trends_list = []
        if trow:
            trends_list = [dict(r) for r in conn.execute(
                "SELECT source, seed_term, kind, query, value FROM trends "
                "WHERE run_id = ? ORDER BY kind, value DESC", (trow["run_id"],)
            ).fetchall()]

    return {
        "summary": {
            "runs": n_runs, "posts": n_posts, "drafts": n_drafts,
            "spend": round(spend or 0, 4), "market": config.MARKET_LABEL,
        },
        "runs": runs,
        "patterns": patterns,
        "drafts": {"run_id": draft_run, "listings": listings},
        "trends": trends_list,
    }


def write(path: str = SNAPSHOT_PATH) -> str:
    """Build a snapshot from SQLite and write it to JSON for committing."""
    data = build()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def load(path: str = SNAPSHOT_PATH) -> dict:
    """Load a previously written snapshot (used when no local DB is present)."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_data() -> dict:
    """Live SQLite if available (local dev), else the committed snapshot (Vercel).

    On Vercel (VERCEL=1, read-only FS) always use the committed snapshot, even if
    a stray DB file was uploaded.
    """
    if os.path.exists(config.DB_PATH) and not os.getenv("VERCEL"):
        return build()
    return load()


if __name__ == "__main__":
    p = write()
    print(f"Snapshot written -> {p}")
