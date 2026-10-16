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
        _failures.clear()


# --- Failed-login limit (OWASP A07) -----------------------------------------
# After LOGIN_MAX_FAILURES wrong passwords for the same email within
# LOGIN_WINDOW_SECONDS, login is refused until the window passes. Unknown
# emails are counted too, so the answer never reveals which emails exist.
LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "900"))

_failures: dict[str, deque] = defaultdict(deque)


def _login_key(email: str) -> str:
    return email.strip().lower()


def login_blocked(email: str) -> int | None:
    """Seconds the caller must wait, or None if login is allowed."""
    now = time.monotonic()
    key = _login_key(email)
    with _lock:
        fails = _failures[key]
        while fails and now - fails[0] >= LOGIN_WINDOW_SECONDS:
            fails.popleft()
        if len(fails) >= LOGIN_MAX_FAILURES:
            return max(1, int(LOGIN_WINDOW_SECONDS - (now - fails[0])) + 1)
        if not fails:
            _failures.pop(key, None)
        return None


def record_login_failure(email: str) -> None:
    with _lock:
        _failures[_login_key(email)].append(time.monotonic())


def clear_login_failures(email: str) -> None:
    with _lock:
        _failures.pop(_login_key(email), None)
