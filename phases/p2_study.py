"""
Phase 2 — Study.

Computes an engagement score per collected post, takes the top
config.TOP_PERCENT_TO_STUDY, and sends them to Claude (Haiku) in batched calls
that return structured JSON (hook type, format, caption structure, hashtag
strategy, CTA style, topic). Aggregates into one `pattern_reports` row.

Standalone debug:  python -m phases.p2_study <run_id>

STATUS: scaffold stub — implemented in deliverable 3.
"""

import config


def study(run_id: str) -> int:
    """Analyze top posts, store a pattern report, return its row id."""
    raise NotImplementedError("Phase 2 study lands in deliverable 3.")


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "debug"
    print(f"[p2] would study top {int(config.TOP_PERCENT_TO_STUDY*100)}% for run {rid}")
