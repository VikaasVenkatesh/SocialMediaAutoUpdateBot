"""
Phase 1 — Collect.

Pulls YouTube video metadata via the free Data API v3 and loads the manual
`seed_posts.csv`, normalizing every row into the `posts` table. Caps the total
at config.MAX_POSTS_PER_RUN.

Standalone debug:  python -m phases.p1_collect <run_id>

STATUS: scaffold stub — implemented in deliverable 2.
"""

import config


def collect(run_id: str) -> int:
    """Collect from all free sources, write normalized rows, return count."""
    raise NotImplementedError("Phase 1 collector lands in deliverable 2.")


if __name__ == "__main__":
    import sys
    rid = sys.argv[1] if len(sys.argv) > 1 else "debug"
    print(f"[p1] would collect up to {config.MAX_POSTS_PER_RUN} posts for run {rid}")
