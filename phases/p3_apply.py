"""
Phase 3 — Apply.

For each listing in config.LISTINGS, calls Claude (Sonnet) with the pattern
report + the listing + config.BRAND_BRIEF and returns, per target platform: a
hook, full caption, hashtag set, suggested format, and a 3–5 line short-video
outline. Stores rows in `drafts` linked to the pattern report.

Standalone debug:  python -m phases.p3_apply <run_id> <pattern_report_id>

STATUS: scaffold stub — implemented in deliverable 4.
"""

import config


def apply(run_id: str, pattern_report_id: int) -> int:
    """Generate drafts for every listing/platform, return count written."""
    raise NotImplementedError("Phase 3 apply lands in deliverable 4.")


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "debug"
    print(f"[p3] would draft for {len(config.LISTINGS)} listing(s) x "
          f"{len(config.TARGET_PLATFORMS)} platforms, run {rid}")
