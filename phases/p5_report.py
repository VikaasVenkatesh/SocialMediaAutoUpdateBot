"""
Phase 5 — Report.

Writes output/digest_<date>.md: this run's top patterns, the per-listing drafts
ready for review, and (if not the first run) what changed since last time.
Prints the file path and estimated token spend.

Standalone debug:  python -m phases.p5_report <run_id>

STATUS: scaffold stub — implemented in deliverable 5.
"""


def report(run_id: str, compare_md: str = "") -> str:
    """Write the markdown digest, return its file path."""
    raise NotImplementedError("Phase 5 report lands in deliverable 5.")


if __name__ == "__main__":
    print("[p5] would write output/digest_<date>.md")
