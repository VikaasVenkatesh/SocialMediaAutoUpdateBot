"""
SQLite schema + tiny helpers for the Real Estate Content Agent PoC.

One local file (config.DB_PATH). No hosted database — keeps the PoC at $0.
Call init_db() once at the start of a run; it is idempotent.
"""

import os
import sqlite3
from contextlib import contextmanager

import config

SCHEMA = """
-- Normalized collected content from all sources (Phase 1).
CREATE TABLE IF NOT EXISTS posts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    platform         TEXT    NOT NULL,        -- youtube | instagram | x | linkedin
    post_url         TEXT,
    author           TEXT,
    posted_at        TEXT,                    -- ISO8601 if known
    format           TEXT,                    -- short | long | image | carousel | text
    caption_text     TEXT,
    likes            INTEGER DEFAULT 0,
    comments         INTEGER DEFAULT 0,
    shares           INTEGER DEFAULT 0,       -- shares OR saves
    views            INTEGER DEFAULT 0,
    engagement_score REAL    DEFAULT 0,       -- computed in Phase 2
    source           TEXT,                    -- youtube_api | seed_csv | meta_api
    run_id           TEXT    NOT NULL,        -- groups rows by run
    collected_at     TEXT    NOT NULL,
    UNIQUE(platform, post_url, run_id)
);

-- One aggregated pattern report per run (Phase 2).
CREATE TABLE IF NOT EXISTS pattern_reports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    posts_studied INTEGER NOT NULL,
    report_json   TEXT    NOT NULL,           -- aggregated structured patterns
    summary       TEXT                        -- short human-readable summary
);

-- Generated, approval-ready drafts (Phase 3).
CREATE TABLE IF NOT EXISTS drafts (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            TEXT    NOT NULL,
    created_at        TEXT    NOT NULL,
    listing_address   TEXT    NOT NULL,
    platform          TEXT    NOT NULL,
    hook              TEXT,
    caption           TEXT,
    hashtags          TEXT,
    suggested_format  TEXT,
    video_outline     TEXT,
    pattern_report_id INTEGER,
    FOREIGN KEY(pattern_report_id) REFERENCES pattern_reports(id)
);

-- Lightweight run ledger incl. estimated token spend (cost guardrail).
CREATE TABLE IF NOT EXISTS runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    posts_collected INTEGER DEFAULT 0,
    est_input_tokens  INTEGER DEFAULT 0,
    est_output_tokens INTEGER DEFAULT 0,
    est_cost_usd      REAL    DEFAULT 0,
    notes           TEXT
);
"""


@contextmanager
def get_conn():
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


if __name__ == "__main__":
    init_db()
    print(f"Initialized schema in {config.DB_PATH}")
