"""`FRONTEND_ORIGIN` parsing (app.main).

Every failure mode here is silent -- a misparsed origin produces a
browser-only CORS error, an empty `allow_origins` entry that looks
plausible in a dashboard, and no server-side log at all. So the parsing
is pinned directly rather than left to be discovered against a deployed
environment.

`app.main` reads the variable at import time, so each case re-imports the
module under a patched environment rather than mutating a live app.
"""

import importlib
import os
from unittest.mock import patch

DEFAULT = "http://localhost:5173"
DEPLOYED = "https://graphmind-web.onrender.com"


def _resolved_origin(value):
    """Re-imports `app.main` with FRONTEND_ORIGIN set to `value` (or unset
    if `value is None`) and returns the origin it resolved to."""
    env = dict(os.environ)
    env.pop("FRONTEND_ORIGIN", None)
    if value is not None:
        env["FRONTEND_ORIGIN"] = value
    with patch.dict(os.environ, env, clear=True):
        import app.main

        return importlib.reload(app.main).FRONTEND_ORIGIN


def test_unset_falls_back_to_local_dev_origin():
    assert _resolved_origin(None) == DEFAULT


def test_blank_is_treated_as_unset_not_as_an_empty_allowlist():
    """The regression this module exists for. `os.environ.get(k, default)`
    returns the default only when the key is ABSENT -- a key set to "" gives
    back "", and `allow_origins=[""]` matches nothing, rejecting every
    cross-origin request including the local dev one. Deploying a backend
    before its frontend URL exists means setting this blank deliberately,
    so "set but empty" is a real state, not a typo."""
    assert _resolved_origin("") == DEFAULT
    assert _resolved_origin("   ") == DEFAULT


def test_trailing_slash_is_stripped_to_match_the_origin_header():
    """A browser's `Origin` is scheme://host[:port] with no trailing
    slash, so a pasted "https://example.com/" would never match and would
    fail exactly like the blank case."""
    assert _resolved_origin(DEPLOYED + "/") == DEPLOYED


def test_surrounding_whitespace_is_stripped():
    """Copy-paste into a dashboard field readily carries a trailing
    newline or space, which is invisible there and fatal here."""
    assert _resolved_origin(f"  {DEPLOYED}\n") == DEPLOYED


def test_a_normal_value_is_passed_through_unchanged():
    assert _resolved_origin(DEPLOYED) == DEPLOYED
