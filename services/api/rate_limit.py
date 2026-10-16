"""Simple per-user rate limit for endpoints that call the language model.

Each user gets MAX_REQUESTS model calls per WINDOW_SECONDS. Past that, the
request is refused until the oldest call falls out of the window. This stops
a stuck script or a bad actor from running up the LLM bill.

Limits can be changed with environment variables (see .env.example).
Note: the counts live in memory, so each API process keeps its own count.
"""
import os
import threading
import time
from collections import defaultdict, deque

MAX_REQUESTS = int(os.environ.get("AGENT_RATE_LIMIT_MAX", "10"))
WINDOW_SECONDS = int(os.environ.get("AGENT_RATE_LIMIT_WINDOW_SECONDS", "60"))

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def check_rate_limit(user_id: str) -> int | None:
    """Count one model call for this user.

    Returns None if the call is allowed, or the number of seconds the user
    must wait if they are over the limit.
    """
    now = time.monotonic()
    with _lock:
        hits = _hits[str(user_id)]
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= MAX_REQUESTS:
            return max(1, int(WINDOW_SECONDS - (now - hits[0])) + 1)
        hits.append(now)
        return None


def reset() -> None:
    """Forget all counts. Used by tests."""
    with _lock:
        _hits.clear()
