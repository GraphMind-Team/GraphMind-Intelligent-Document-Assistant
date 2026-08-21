"""`app.shared.env.env_str` (added after two production outages).

Both were a dashboard value carrying invisible whitespace, and neither
produced a server-side error naming the real cause:

  * FRONTEND_ORIGIN set blank -> allow_origins=[""] matched nothing, so
    every cross-origin request was rejected.
  * OPENROUTER_API_KEY pasted with a trailing newline -> httpx refused to
    send the header at all (header-injection protection), surfacing as
    "entity extraction failed after 3 attempts", which reads like a
    provider outage and is not one.
"""

import os
from unittest.mock import patch

from app.shared.env import env_str

DEFAULT = "fallback-value"


def _with_env(value):
    env = dict(os.environ)
    env.pop("SOME_KEY", None)
    if value is not None:
        env["SOME_KEY"] = value
    return patch.dict(os.environ, env, clear=True)


def test_absent_returns_the_default():
    with _with_env(None):
        assert env_str("SOME_KEY", DEFAULT) == DEFAULT


def test_blank_returns_the_default_not_an_empty_string():
    """`os.environ.get(k, default)` gets this wrong -- it returns the
    default only when the key is ABSENT."""
    with _with_env(""):
        assert env_str("SOME_KEY", DEFAULT) == DEFAULT
    with _with_env("   "):
        assert env_str("SOME_KEY", DEFAULT) == DEFAULT


def test_trailing_newline_is_stripped():
    """The OpenRouter outage exactly: a pasted secret with a trailing
    newline is an illegal HTTP header value, so the request never leaves
    the process."""
    with _with_env("sk-or-v1-abc123\n"):
        assert env_str("SOME_KEY") == "sk-or-v1-abc123"


def test_surrounding_whitespace_is_stripped():
    with _with_env("  https://example.com \n"):
        assert env_str("SOME_KEY") == "https://example.com"


def test_a_clean_value_passes_through_unchanged():
    with _with_env("sk-or-v1-abc123"):
        assert env_str("SOME_KEY") == "sk-or-v1-abc123"


def test_no_default_given_yields_empty_string():
    with _with_env(None):
        assert env_str("SOME_KEY") == ""
