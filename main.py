"""
Real Estate Content Agent — PoC entry point.

Runs the loop in order: Collect -> Study -> Apply -> Compare -> Report.
Manual trigger only (no scheduler in the PoC):

    python main.py

Each phase also runs standalone for debugging, e.g. `python -m phases.p1_collect`.

STATUS: deliverable 1 wires the orchestration skeleton. Phases 1–5 are stubs
until later deliverables; running now will stop at Phase 1 with a clear
NotImplementedError, which is expected for the scaffold.
"""

import datetime as dt
import uuid

import config
import db
from phases import p1_collect, p2_study, p3_apply, p4_compare, p5_report


def new_run_id() -> str:
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:6]}"


def main():
    db.init_db()
    run_id = new_run_id()
    started = dt.datetime.now().isoformat(timespec="seconds")
    with db.get_conn() as conn:
        conn.execute(
            "INSERT INTO runs(run_id, started_at) VALUES (?, ?)", (run_id, started)
        )
    print(f"=== Run {run_id} ===")
    print(f"Markets: {config.MARKET_LABEL}")
    print(f"Cap: {config.MAX_POSTS_PER_RUN} posts/run\n")

    # Phase 1 — Collect
    n = p1_collect.collect(run_id)
    print(f"[1] collected {n} posts")

    # Phase 2 — Study
    report_id = p2_study.study(run_id)
    print(f"[2] pattern report #{report_id}")

    # Phase 3 — Apply
    drafted = p3_apply.apply(run_id, report_id)
    print(f"[3] generated {drafted} drafts")

    # Phase 4 — Compare
    compare_md = p4_compare.compare(run_id)
    print("[4] compared against previous run")

    # Phase 5 — Report
    path = p5_report.report(run_id, compare_md)
    print(f"[5] digest written -> {path}")


if __name__ == "__main__":
    main()
