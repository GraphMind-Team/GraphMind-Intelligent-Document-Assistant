"""`app.shared.rate_limiter` unit coverage.

The limiters' *routing* behaviour is covered where they're wired up
(`test_auth_login.py`, `test_documents_upload.py`, `test_chat_rate_limit.py`).
What's covered here is the mechanism itself, and specifically the key
reclamation in `RateLimiter._prune_locked` -- a property no route-level
test can observe, since it's about what the dict retains across many
calls rather than about any one response.
"""

import time

import pytest
from fastapi import HTTPException

from app.shared.rate_limiter import _MAX_KEYS_SWEPT_PER_CHECK, ConcurrencyLimiter, RateLimiter


def test_allows_up_to_the_budget_then_refuses():
    limiter = RateLimiter(max_attempts=3, window_seconds=60.0, detail="nope")

    for _ in range(3):
        limiter.check("key")

    with pytest.raises(HTTPException) as excinfo:
        limiter.check("key")
    assert excinfo.value.status_code == 429
    assert excinfo.value.detail == "nope"


def test_distinct_key_parts_get_distinct_budgets():
    limiter = RateLimiter(max_attempts=1, window_seconds=60.0)
    limiter.check("ip", "a@example.com")
    limiter.check("ip", "b@example.com")  # different key, own budget

    with pytest.raises(HTTPException):
        limiter.check("ip", "a@example.com")


def test_reset_clears_a_keys_history():
    limiter = RateLimiter(max_attempts=1, window_seconds=60.0)
    limiter.check("key")
    limiter.reset("key")
    limiter.check("key")  # does not raise


def test_attempts_outside_the_window_stop_counting():
    limiter = RateLimiter(max_attempts=1, window_seconds=0.05)
    limiter.check("key")
    time.sleep(0.1)
    limiter.check("key")  # the first attempt has aged out


def test_a_refused_attempt_does_not_extend_the_window():
    """Being refused must not itself count as a fresh attempt -- otherwise
    a caller hammering the endpoint keeps its own lockout alive forever
    and the window never drains."""
    limiter = RateLimiter(max_attempts=1, window_seconds=0.15)
    limiter.check("key")

    for _ in range(5):
        with pytest.raises(HTTPException):
            limiter.check("key")
        time.sleep(0.03)

    time.sleep(0.15)
    limiter.check("key")  # the original attempt aged out despite the hammering


def test_stale_keys_are_reclaimed_even_behind_a_full_sweep_window_of_hot_keys():
    """Regression: `_prune_locked` bounds its sweep with `islice`, which
    always starts at the dict's head. With plain insertion ordering, any
    key parked at the head that keeps being refreshed shadows everything
    behind it -- so the rotating keys the sweep exists to reclaim
    accumulated forever, unreached, which is a slow memory leak on a
    long-lived process.

    Uses exactly `_MAX_KEYS_SWEPT_PER_CHECK` hot keys, since that is the
    threshold at which the sweep window is entirely consumed by them, and
    inserts them *before* the cold ones so they occupy the head under
    plain insertion ordering.

    The hot keys must be kept continuously fresh for this to test
    anything: letting them all age out first makes the head go stale too,
    the sweep reclaims it, the cold keys shift up, and even the unfixed
    implementation drains -- a version of this test that slept through the
    whole window passed against the bug. So the refresh loop below
    re-checks every hot key at an interval well inside the window, which
    is what pins them in front of the sweep. Before the fix that retained
    all 200 cold keys indefinitely; `move_to_end` in `check` is what keeps
    the head pointed at the least-recently-checked end instead.
    """
    window_seconds = 0.3
    limiter = RateLimiter(max_attempts=10_000, window_seconds=window_seconds)
    cold_key_count = 200

    for hot in range(_MAX_KEYS_SWEPT_PER_CHECK):
        limiter.check("hot", str(hot))
    for tick in range(cold_key_count):
        limiter.check("cold", str(tick))

    # Hold the hot keys fresh for longer than a full window, so the cold
    # keys age out while the head never does.
    deadline = time.monotonic() + window_seconds * 2
    while time.monotonic() < deadline:
        for hot in range(_MAX_KEYS_SWEPT_PER_CHECK):
            limiter.check("hot", str(hot))
        time.sleep(window_seconds / 10)

    remaining_cold = [key for key in limiter._attempts if key[0] == "cold"]
    assert remaining_cold == []


def test_pruning_never_drops_a_key_still_inside_its_window():
    """The sweep must only reclaim genuinely stale keys -- dropping a live
    one would silently hand a caller a fresh budget mid-window."""
    limiter = RateLimiter(max_attempts=1, window_seconds=60.0)
    limiter.check("victim")

    # Plenty of unrelated traffic, each call running a sweep.
    for i in range(_MAX_KEYS_SWEPT_PER_CHECK * 3):
        limiter.check("noise", str(i))

    with pytest.raises(HTTPException):
        limiter.check("victim")  # still counted, not reclaimed


def test_concurrency_limiter_admits_up_to_max_then_refuses():
    limiter = ConcurrencyLimiter(max_concurrent=2, detail="busy")

    with limiter.slot("k"), limiter.slot("k"):
        with pytest.raises(HTTPException) as excinfo:
            with limiter.slot("k"):
                pass
        assert excinfo.value.status_code == 429
        assert excinfo.value.detail == "busy"


def test_concurrency_limiter_drops_the_key_once_it_empties():
    """The in-flight dict tracks only currently-active keys -- a key left
    behind at 0 would make it grow by one entry per caller, forever."""
    limiter = ConcurrencyLimiter(max_concurrent=1)

    with limiter.slot("k"):
        pass
    assert "k" not in limiter._in_flight

    # A refused admission must not leave a 0-valued entry behind either.
    with limiter.slot("k"):
        with pytest.raises(HTTPException):
            with limiter.slot("k"):
                pass
    assert "k" not in limiter._in_flight
