"""In-process rate limiter for POST /auth/login and POST /auth/register.

Per-process, fixed-window counter keyed on whatever `check()`/`reset()` are
called with -- (client IP, normalized email) for login, client IP alone
for registration (there's no existing account to key off of, and the
attack this guards against -- enumeration via 409 vs. 201, or mass account
creation -- is one source hammering many different emails, so per-IP is
the right key there). Not distributed -- correct for a single-process
dev/MVP deployment; would need a shared store (e.g. Redis) behind multiple
workers/instances.

Exposed via FastAPI dependencies (`get_login_rate_limiter`,
`get_register_rate_limiter`) that return the limiter *instance*, not a
pre-checked result -- a FastAPI dependency is resolved independently of
body parsing, so it cannot see `LoginRequest.email` itself for the login
case. Each route calls `limiter.check(...)` once it has whatever key parts
it needs. `login` follows up with `limiter.reset(...)` on success so
legitimate repeat logins don't erode the same budget as failed guesses;
`register` has no equivalent reset call -- a given email can only register
once, so there's no "legitimate repeat" to protect. Tests substitute a
fresh instance via `app.dependency_overrides`, exactly like `get_db_session`.
"""

import itertools
import threading
import time
from collections import defaultdict

from fastapi import HTTPException

_MAX_ATTEMPTS = 5
_WINDOW_SECONDS = 60.0
# Bound on how many keys we examine per check() call, so a single request
# doesn't pay for an unbounded full-dict scan.
_MAX_KEYS_SWEPT_PER_CHECK = 50


class RateLimiter:
    def __init__(
        self,
        max_attempts: int = _MAX_ATTEMPTS,
        window_seconds: float = _WINDOW_SECONDS,
        detail: str = "Too many attempts. Try again later.",
    ):
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._detail = detail
        self._lock = threading.Lock()
        self._attempts: dict[tuple[str, ...], list[float]] = defaultdict(list)

    def _prune_locked(self, now: float) -> None:
        """Drops empty/expired keys so the dict doesn't grow unbounded
        under rotating-key hammering. Must be called with `self._lock`
        held. Bounded per call -- caps keys *examined*, not keys found
        stale, via `itertools.islice` over the dict iteration itself.
        Counting only stale hits (the old approach) degenerates into a
        full O(n) scan whenever every key is fresh (e.g. an attacker
        rotating emails so nothing is ever stale), on a dict that grows by
        one entry per unique key."""
        window_start = now - self._window_seconds
        stale_keys = [
            key
            for key, timestamps in itertools.islice(self._attempts.items(), _MAX_KEYS_SWEPT_PER_CHECK)
            if not any(t > window_start for t in timestamps)
        ]
        for key in stale_keys:
            del self._attempts[key]

    def check(self, *key_parts: str) -> None:
        """Raises HTTPException(429) once `key_parts`'s 6th attempt lands
        within the window (5 allowed); otherwise records this attempt.
        Counts every attempt, success or failure -- callers that succeed
        and want repeats exempted should follow up with `reset()`."""
        key = key_parts
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            window_start = now - self._window_seconds
            attempts = [t for t in self._attempts[key] if t > window_start]
            if len(attempts) >= self._max_attempts:
                self._attempts[key] = attempts
                raise HTTPException(status_code=429, detail=self._detail)
            attempts.append(now)
            self._attempts[key] = attempts

    def reset(self, *key_parts: str) -> None:
        """Clears `key_parts`'s attempt history -- called after a
        successful login so legitimate repeat logins don't count against
        the same budget as failed guesses."""
        key = key_parts
        with self._lock:
            self._attempts.pop(key, None)


_default_login_limiter = RateLimiter(detail="Too many login attempts. Try again later.")
_default_register_limiter = RateLimiter(detail="Too many registration attempts. Try again later.")


def get_login_rate_limiter() -> RateLimiter:
    return _default_login_limiter


def get_register_rate_limiter() -> RateLimiter:
    return _default_register_limiter
