"""In-process request limiters, shared across feature modules.

Two independent mechanisms, guarding two different failure modes:

- `RateLimiter` -- fixed-window counter: "how many requests over time".
  Guards sustained abuse (credential guessing, mass account creation,
  scripted bulk uploads filling Postgres).
- `ConcurrencyLimiter` -- in-flight gauge: "how many requests at once".
  Guards a single burst exhausting memory. Rate limiting alone doesn't
  cover this: 50 simultaneous 20MB uploads are 50 requests in one
  instant, which a per-minute window happily permits.

Neither is distributed -- both are correct for the single-process MVP
deployment and would need a shared store (e.g. Redis) behind multiple
workers/instances.

Lives in `shared/` rather than any one feature module because `auth`
(login/register) and `documents` (upload) both depend on it. Exposed via
FastAPI dependencies that return the limiter *instance*, not a pre-checked
result, so a route can call `check(...)` once it has whatever key parts it
needs (a dependency is resolved independently of body parsing, so it can't
see request-body fields itself). Tests substitute fresh instances via
`app.dependency_overrides`, exactly like `get_db_session`.
"""

import itertools
import threading
import time
from collections import OrderedDict, defaultdict
from contextlib import contextmanager

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
        # Ordered least-recently-checked first -- see `_prune_locked` for
        # why that ordering is what makes the bounded sweep actually reach
        # stale keys. An `OrderedDict`, not a plain `dict`, purely for
        # `move_to_end`: plain dicts preserve insertion order but offer no
        # O(1) way to re-order one key without deleting and reinserting it.
        self._attempts: OrderedDict[tuple[str, ...], list[float]] = OrderedDict()

    def _prune_locked(self, now: float) -> None:
        """Drops empty/expired keys so the dict doesn't grow unbounded
        under rotating-key hammering. Must be called with `self._lock`
        held. Bounded per call -- caps keys *examined*, not keys found
        stale, via `itertools.islice` over the dict iteration itself.
        Counting only stale hits (the old approach) degenerates into a
        full O(n) scan whenever every key is fresh (e.g. an attacker
        rotating emails so nothing is ever stale), on a dict that grows by
        one entry per unique key.

        The bound alone is not enough, though, and this is what the
        `move_to_end` in `check` exists for: `islice` always starts from
        the dict's head, so with a plain insertion-ordered dict the sweep
        re-examines the same first `_MAX_KEYS_SWEPT_PER_CHECK` keys on
        every call. Any key parked at the head that keeps being refreshed
        -- 50 active accounts is enough -- permanently shadows everything
        behind it, and the rotating keys this function exists to reclaim
        accumulate forever, unreached. Measured before the fix: 50 hot
        keys plus 200 one-shot keys left all 200 stale entries retained
        indefinitely.
        `check` moves each key it touches to the *back*, so the head is
        always the least-recently-checked end -- precisely where stale
        keys collect -- and a hot key can never sit in front of the sweep.
        """
        window_start = now - self._window_seconds
        stale_keys = [
            key
            for key, timestamps in itertools.islice(self._attempts.items(), _MAX_KEYS_SWEPT_PER_CHECK)
            if not any(t > window_start for t in timestamps)
        ]
        for key in stale_keys:
            del self._attempts[key]

    def check(self, *key_parts: str) -> None:
        """Raises HTTPException(429) once `key_parts` exceeds the allowed
        attempts within the window; otherwise records this attempt.
        Counts every attempt, success or failure -- callers that succeed
        and want repeats exempted should follow up with `reset()`."""
        key = key_parts
        now = time.monotonic()
        with self._lock:
            self._prune_locked(now)
            window_start = now - self._window_seconds
            # `.get`, not a `defaultdict` read: an over-limit key below
            # raises without ever needing the entry to have been created,
            # and this keeps "was this key present" honest for the
            # `move_to_end` bookkeeping.
            attempts = [t for t in self._attempts.get(key, []) if t > window_start]
            if len(attempts) >= self._max_attempts:
                self._attempts[key] = attempts
                self._attempts.move_to_end(key)
                raise HTTPException(status_code=429, detail=self._detail)
            attempts.append(now)
            self._attempts[key] = attempts
            # Keeps this key out of the sweep window above until every
            # other key has been considered -- see `_prune_locked`.
            self._attempts.move_to_end(key)

    def reset(self, *key_parts: str) -> None:
        """Clears `key_parts`'s attempt history -- called after a
        successful login so legitimate repeat logins don't count against
        the same budget as failed guesses."""
        key = key_parts
        with self._lock:
            self._attempts.pop(key, None)


class ConcurrencyLimiter:
    """Caps how many requests one key may have *in flight simultaneously*.

    Used as a context manager so the slot is always released, including on
    an exception mid-request:

        with limiter.slot(str(user.id)):
            ...  # handle the upload

    Distinct from `RateLimiter`, which bounds requests per unit of time --
    a burst of N simultaneous requests is a single instant to a fixed
    window, so only this catches it. A key's counter is deleted on release
    when it hits zero, so the dict tracks only currently-active keys and
    can't grow unbounded.
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        detail: str = "Too many requests in progress. Try again shortly.",
    ):
        self._max_concurrent = max_concurrent
        self._detail = detail
        self._lock = threading.Lock()
        self._in_flight: dict[str, int] = defaultdict(int)

    @contextmanager
    def slot(self, key: str):
        with self._lock:
            if self._in_flight[key] >= self._max_concurrent:
                # Don't leave a 0-valued key behind from the defaultdict
                # read above when we're rejecting rather than admitting.
                if self._in_flight[key] == 0:
                    del self._in_flight[key]
                raise HTTPException(status_code=429, detail=self._detail)
            self._in_flight[key] += 1
        try:
            yield
        finally:
            with self._lock:
                self._in_flight[key] -= 1
                if self._in_flight[key] <= 0:
                    del self._in_flight[key]
