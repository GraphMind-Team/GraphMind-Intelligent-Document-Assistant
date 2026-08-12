"""In-process rate limiter for POST /auth/login.

Per-process, per-(client IP, normalized email) fixed-window counter. Not
distributed -- correct for a single-process dev/MVP deployment; would need
a shared store (e.g. Redis) behind multiple workers/instances.

Exposed via a FastAPI dependency (`get_login_rate_limiter`) that returns
the limiter *instance*, not a pre-checked result -- a FastAPI dependency
is resolved independently of body parsing, so it cannot see
`LoginRequest.email` itself. The route calls `limiter.check(ip, email)`
once it has both the client IP and the parsed, normalized email, and
`limiter.reset(ip, email)` after a successful login so legitimate repeat
logins don't erode the same budget as failed guesses. Tests substitute a
fresh instance via `app.dependency_overrides`, exactly like `get_db_session`.
"""

import threading
import time
from collections import defaultdict

from fastapi import HTTPException

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 60.0
# Bound on how many stale keys we sweep per check() call, so a single
# request doesn't pay for an unbounded full-dict scan.
_MAX_KEYS_SWEPT_PER_CHECK = 50


class LoginRateLimiter:
    def __init__(self, max_attempts: int = _MAX_ATTEMPTS, window_seconds: float = _WINDOW_SECONDS):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._lock = threading.Lock()
        self._attempts: dict[tuple[str, str], list[float]] = defaultdict(list)

    def _prune_locked(self, now: float) -> None:
        """Drops empty/expired keys so the dict doesn't grow unbounded
        under random-email hammering. Must be called with `self._lock`
        held. Bounded per call -- not a full sweep every time."""
        window_start = now - self._window_seconds
        stale_keys = []
        for key, timestamps in self._attempts.items():
            if len(stale_keys) >= _MAX_KEYS_SWEPT_PER_CHECK:
                break
            if not any(t > window_start for t in timestamps):
                stale_keys.append(key)
        for key in stale_keys:
            del self._attempts[key]

    def check(self, ip: str, email: str) -> None:
        """Raises HTTPException(429) once the (ip, email) pair's 6th
        attempt lands within the window (5 allowed); otherwise records
        this attempt. Counts every attempt, success or failure -- callers
        that succeed should follow up with `reset()`."""
        key = (ip, email)
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            window_start = now - self._window_seconds
            attempts = [t for t in self._attempts[key] if t > window_start]
            if len(attempts) >= self._max_attempts:
                self._attempts[key] = attempts
                raise HTTPException(
                    status_code=429, detail="Too many login attempts. Try again later."
                )
            attempts.append(now)
            self._attempts[key] = attempts

    def reset(self, ip: str, email: str) -> None:
        """Clears the (ip, email) pair's attempt history -- called after a
        successful login so legitimate repeat logins don't count against
        the same budget as failed guesses."""
        key = (ip, email)
        with self._lock:
            self._attempts.pop(key, None)


_default_limiter = LoginRateLimiter()


def get_login_rate_limiter() -> LoginRateLimiter:
    return _default_limiter
