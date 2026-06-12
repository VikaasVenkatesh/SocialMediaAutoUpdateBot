"""
Phase 4 — Compare (the seed of the loop).

On any run after the first, diff this run's pattern report against the previous
run's and note what changed (dominant pattern shifts per field). Enough to show
the loop is cumulative; full performance feedback comes once posting is wired up.

Standalone debug:  python -m phases.p4_compare [run_id]
"""

import json

import db


def _latest_two_reports(run_id):
    """Return (this_report, prev_report) as dicts, prev may be None."""
    with db.get_conn() as conn:
        this = conn.execute(
            "SELECT id, run_id, report_json, created_at FROM pattern_reports "
            "WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (run_id,),
        ).fetchone()
        if not this:
            return None, None
        prev = conn.execute(
            "SELECT id, run_id, report_json, created_at FROM pattern_reports "
            "WHERE id < ? ORDER BY id DESC LIMIT 1",
            (this["id"],),
        ).fetchone()
    return this, prev


def _dominants(report_row):
    patterns = json.loads(report_row["report_json"]).get("patterns", {})
    return {field: info.get("dominant") for field, info in patterns.items()}


def compare(run_id: str) -> str:
    """Return a short markdown diff vs the previous run ('' framing on first run)."""
    this, prev = _latest_two_reports(run_id)
    if not this:
        return "_No pattern report for this run._"
    if not prev:
        return ("_First run — no previous pattern report to compare against. "
                "The next run will diff against this one._")

    cur, old = _dominants(this), _dominants(prev)
    fields = sorted(set(cur) | set(old))
    changed, steady = [], []
    for f in fields:
        a, b = old.get(f), cur.get(f)
        if a != b:
            changed.append(f"- **{f}**: `{a}` → `{b}`")
        else:
            steady.append(f"- **{f}**: `{b}` (unchanged)")

    lines = [
        f"Comparing run `{this['run_id']}` against previous run "
        f"`{prev['run_id']}`.",
        "",
        f"**Changed ({len(changed)}):**",
    ]
    lines += changed or ["- _none_"]
    lines += ["", f"**Steady ({len(steady)}):**"]
    lines += steady or ["- _none_"]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    rid = sys.argv[1] if len(sys.argv) > 1 else None
    if not rid:
        with db.get_conn() as conn:
            row = conn.execute(
                "SELECT run_id FROM pattern_reports ORDER BY id DESC LIMIT 1"
            ).fetchone()
            rid = row["run_id"] if row else "none"
    print(compare(rid))
