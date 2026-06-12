"""
Tiny dependency-free rate limiter for the Generate endpoint.

Fixed-window counters held in memory. On a single (local) process this is exact.
On Vercel it holds within a warm container and resets on cold starts — combined
with the password it stops bursts/accidental spam, but is NOT a hard
cross-instance guarantee. For that, back it with Upstash Redis / Vercel KV
(see README "rate limiting" note).
"""

import threading
import time

_lock = threading.Lock()
_hits: dict[str, list[float]] = {}


def check(key: str, limit: int, window_seconds: int):
    """Record a hit for `key`. Returns (allowed, retry_after_seconds).

    Does NOT consume the slot when the limit is already reached.
    """
    now = time.time()
    cutoff = now - window_seconds
    with _lock:
        hits = [t for t in _hits.get(key, []) if t > cutoff]
        if len(hits) >= limit:
            oldest = hits[0] if hits else now
            retry_after = int(oldest + window_seconds - now) + 1
            _hits[key] = hits
            return False, max(retry_after, 1)
        hits.append(now)
        _hits[key] = hits
        return True, 0


def check_many(checks):
    """Apply several (key, limit, window) checks. First failure wins.

    Only consumes a slot for a check once all prior checks passed, so a global
    cap isn't burned by a request the per-IP cap would have rejected.
    """
    # Peek all first (non-consuming) to find the binding limit.
    now = time.time()
    with _lock:
        for key, limit, window in checks:
            cutoff = now - window
            hits = [t for t in _hits.get(key, []) if t > cutoff]
            _hits[key] = hits
            if len(hits) >= limit:
                oldest = hits[0] if hits else now
                retry_after = int(oldest + window - now) + 1
                return False, max(retry_after, 1)
        # All clear — consume one slot on each.
        for key, limit, window in checks:
            _hits[key].append(now)
    return True, 0
