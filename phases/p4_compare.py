"""
Phase 4 — Compare (the seed of the loop).

On any run after the first, diffs this run's pattern report against the
previous run's and notes what changed. Enough to demonstrate the loop is
cumulative; full performance feedback comes once posting is wired up (later).

Standalone debug:  python -m phases.p4_compare <run_id>

STATUS: scaffold stub — implemented in deliverable 5.
"""


def compare(run_id: str) -> str:
    """Return a short markdown diff vs the previous run (or '' if first run)."""
    raise NotImplementedError("Phase 4 compare lands in deliverable 5.")


if __name__ == "__main__":
    print("[p4] would diff this run's pattern report against the previous run")
