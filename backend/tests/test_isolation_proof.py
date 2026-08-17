"""`scripts/isolation_proof.py` unit coverage (Story 6.2).

Light coverage of the pure/deterministic pieces only -- route-tree
introspection, forged-token construction, report/pass-fail classification
-- never against a live DB/Weaviate/Neo4j/OpenRouter or a real
`TestClient(app)` HTTP call. The live proof itself
(`python -m scripts.isolation_proof`) is the primary artifact; this file
is secondary, per the spec's own Tasks description.

`_find_unscoped_routes`/`_covered_routes` are exercised against the real
`app` object (safe: importing `app.main` never opens a live connection --
`shared/data_access/session.py`'s engine is lazily built on first use, and
route/dependency-tree construction is pure metadata, no I/O). This is a
genuine regression test: if a future endpoint is added without
`Depends(get_current_user)`, this test catches it without touching any
live service.
"""

import uuid

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from app.auth import service as auth_service
from app.auth.dependencies import get_current_user
from app.main import app
from scripts.isolation_proof import (
    ACCOUNT_A_EMAIL,
    ACCOUNT_B_EMAIL,
    _MIN_EXPECTED_COVERED_ROUTES,
    PUBLIC_ALLOWLIST_PATHS,
    CheckResult,
    NAResult,
    _build_unknown_user_token,
    _build_wrong_signature_token,
    _check_auth_password_change_scoped_to_caller,
    _check_auth_theme_patch_scoped_to_caller,
    _check_chat_ask_no_leak,
    _check_forged_token_sweep,
    _check_kg_graph_no_leak,
    _concrete_path,
    _covered_routes,
    _dependency_tree_contains,
    _find_unscoped_routes,
    _primary_method,
    _print_report,
    _should_exit_nonzero,
)


# ---------------------------------------------------------------------------
# Route enumeration -- spec Boundaries row 1 (real app, no live services)
# ---------------------------------------------------------------------------


def test_real_app_has_no_unscoped_routes_outside_the_public_allowlist():
    # The regression test this whole check exists to be: a future endpoint
    # added without Depends(get_current_user) fails this, not just a live
    # run of the script.
    assert _find_unscoped_routes(app) == []


def test_covered_routes_excludes_exactly_the_public_allowlist():
    covered_paths = {route.path for route in _covered_routes(app)}
    assert covered_paths.isdisjoint(PUBLIC_ALLOWLIST_PATHS)
    # Every protected endpoint named in the spec's Boundaries is present.
    assert {"/auth/me", "/documents", "/documents/{document_id}", "/chat/ask", "/kg/graph"} <= covered_paths


def test_covered_routes_meets_the_minimum_expected_count():
    # `_run()` aborts (review finding #4) if `len(_covered_routes(app))`
    # ever drops below `_MIN_EXPECTED_COVERED_ROUTES` -- a silent signal
    # that `_iter_effective_routes`' `_IncludedRouter` ducktyping stopped
    # matching a future FastAPI version's route tree, which would shrink
    # the forged-token sweep and route-enumeration check down to a
    # near-empty, meaningless set without raising anything on its own.
    # This pins today's real count so that abort condition has coverage.
    assert len(_covered_routes(app)) >= _MIN_EXPECTED_COVERED_ROUTES


def test_covered_routes_finds_all_four_auth_me_operations():
    # GET/PATCH/DELETE /auth/me plus PATCH /auth/theme and POST
    # /auth/me/password -- five distinct APIRoute objects sharing (or
    # near-sharing) a path, each its own dependency tree.
    methods_by_path = {}
    for route in _covered_routes(app):
        if route.path in ("/auth/me", "/auth/theme", "/auth/me/password"):
            methods_by_path.setdefault(route.path, set()).update(
                (route.methods or set()) - {"HEAD", "OPTIONS"}
            )
    assert methods_by_path["/auth/me"] == {"GET", "PATCH", "DELETE"}
    assert methods_by_path["/auth/theme"] == {"PATCH"}
    assert methods_by_path["/auth/me/password"] == {"POST"}


def test_dependency_tree_contains_finds_a_top_level_match():
    class _FakeDependant:
        def __init__(self, call, dependencies=()):
            self.call = call
            self.dependencies = dependencies

    target = object()
    dependant = _FakeDependant(call=target)
    assert _dependency_tree_contains(dependant, target) is True


def test_dependency_tree_contains_finds_a_nested_match():
    class _FakeDependant:
        def __init__(self, call, dependencies=()):
            self.call = call
            self.dependencies = dependencies

    target = object()
    leaf = _FakeDependant(call=target)
    middle = _FakeDependant(call=lambda: None, dependencies=[leaf])
    root = _FakeDependant(call=lambda: None, dependencies=[middle])
    assert _dependency_tree_contains(root, target) is True


def test_dependency_tree_contains_returns_false_when_absent():
    class _FakeDependant:
        def __init__(self, call, dependencies=()):
            self.call = call
            self.dependencies = dependencies

    target = object()
    dependant = _FakeDependant(call=lambda: None, dependencies=[_FakeDependant(call=lambda: None)])
    assert _dependency_tree_contains(dependant, target) is False


def _noop_endpoint():
    return {"ok": True}


def test_find_unscoped_routes_flags_a_route_with_no_get_current_user():
    # A genuine APIRoute (real dependant, no Depends(get_current_user))
    # wrapped in a fake app -- proves the detector actually flags
    # something, not just that the real app happens to pass. Isinstance
    # (not duck-typed) on purpose: `_covered_routes` only considers real
    # `APIRoute`s, the same as the real app's route tree.
    route = APIRoute("/fake/protected", _noop_endpoint, methods=["GET"])

    class _FakeApp:
        routes = [route]

    unscoped = _find_unscoped_routes(_FakeApp())
    assert unscoped == [("GET", "/fake/protected")]


def test_find_unscoped_routes_ignores_the_public_allowlist():
    route = APIRoute("/auth/login", _noop_endpoint, methods=["POST"])

    class _FakeApp:
        routes = [route]

    assert _find_unscoped_routes(_FakeApp()) == []


# ---------------------------------------------------------------------------
# Forged-token perimeter sweep -- spec Boundaries row 5
# ---------------------------------------------------------------------------


def test_wrong_signature_token_fails_inside_the_pyjwt_error_branch():
    token = _build_wrong_signature_token()
    with pytest.raises(HTTPException) as exc_info:
        auth_service.decode_access_token(token)
    assert exc_info.value.status_code == 401


def test_unknown_user_token_passes_signature_verification():
    # Genuinely distinct from the wrong-signature token: this one decodes
    # successfully (the 401 for it can only come from get_user_by_id
    # returning None downstream in get_current_user, not from
    # decode_access_token itself).
    token = _build_unknown_user_token()
    user_id = auth_service.decode_access_token(token)
    assert isinstance(user_id, uuid.UUID)


def test_wrong_signature_and_unknown_user_tokens_are_not_the_same_string():
    assert _build_wrong_signature_token() != _build_unknown_user_token()


# ---------------------------------------------------------------------------
# Route -> request shape helpers used by the forged-token sweep
# ---------------------------------------------------------------------------


def test_primary_method_prefers_the_real_verb_over_head_and_options():
    class _FakeRoute:
        methods = {"GET", "HEAD"}

    assert _primary_method(_FakeRoute()) == "GET"


def test_primary_method_returns_none_when_nothing_but_head_or_options():
    class _FakeRoute:
        methods = {"HEAD", "OPTIONS"}

    assert _primary_method(_FakeRoute()) is None


def test_concrete_path_substitutes_every_path_param_with_a_valid_uuid():
    class _FakeRoute:
        path = "/documents/{document_id}"

    concrete = _concrete_path(_FakeRoute())
    assert concrete.startswith("/documents/")
    raw_id = concrete.removeprefix("/documents/")
    assert uuid.UUID(raw_id)  # does not raise


def test_concrete_path_is_a_no_op_when_there_are_no_path_params():
    class _FakeRoute:
        path = "/kg/graph"

    assert _concrete_path(_FakeRoute()) == "/kg/graph"


# ---------------------------------------------------------------------------
# Fake in-process client double for the mutate-and-revert /auth/* checks --
# lets `_check_auth_theme_patch_scoped_to_caller` and
# `_check_auth_password_change_scoped_to_caller`'s real logic run
# end-to-end against simulated two-account state, without a live
# TestClient/DB. This is what gives the two review-flagged bugs (findings
# #1 and #2) genuine regression coverage.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code, body=None, text=None):
        self.status_code = status_code
        self._body = body if body is not None else {}
        # The blending checks read `.text`, not `.json()` -- defaults to
        # `str(body)` so the auth-check fakes (which only ever pass `body`)
        # don't need to care, while the chat/graph fakes below pass `text`
        # explicitly.
        self.text = text if text is not None else str(self._body)

    def json(self):
        return self._body


class _FakeAccount:
    def __init__(self, *, email, password, theme="light"):
        self.email = email
        self.password = password
        self.theme = theme

    def as_me_body(self):
        return {"email": self.email, "theme": self.theme}


class _FakeAuthClient:
    """Minimal double for the handful of `/auth/*` endpoints the two
    checks above call, keyed by bearer token."""

    def __init__(self, accounts_by_token: dict[str, _FakeAccount]):
        self._by_token = accounts_by_token
        self._by_email = {account.email: account for account in accounts_by_token.values()}

    def _account(self, headers):
        token = headers["Authorization"].removeprefix("Bearer ")
        return self._by_token[token]

    def get(self, path, headers):
        assert path == "/auth/me"
        return _FakeResponse(200, self._account(headers).as_me_body())

    def patch(self, path, json, headers):
        if path == "/auth/theme":
            account = self._account(headers)
            account.theme = json["theme"]
            return _FakeResponse(200, {"theme": account.theme})
        raise AssertionError(f"unexpected PATCH {path}")

    def post(self, path, json, headers=None):
        if path == "/auth/me/password":
            account = self._account(headers)
            if json["current_password"] != account.password:
                return _FakeResponse(400, {"detail": "Current password is incorrect."})
            account.password = json["new_password"]
            return _FakeResponse(200, {"detail": "Password updated."})
        if path == "/auth/login":
            account = self._by_email.get(json["email"])
            if account is None or account.password != json["password"]:
                return _FakeResponse(401, {"detail": "Invalid email or password."})
            return _FakeResponse(200, {"access_token": "fake", "token_type": "bearer", "theme": account.theme})
        raise AssertionError(f"unexpected POST {path}")


_HEADERS_A = {"Authorization": "Bearer token-a"}
_HEADERS_B = {"Authorization": "Bearer token-b"}


# ---------------------------------------------------------------------------
# _check_auth_theme_patch_scoped_to_caller -- review finding #1
# ---------------------------------------------------------------------------


def test_theme_check_does_not_flag_a_coincidental_pre_existing_match():
    # A is already "dark"; B starts "light" and switches to "dark" (its own
    # temp value). A's theme was already "dark" *before* B's PATCH ever
    # ran, so this must NOT be reported as a leak -- the pre-fix code only
    # compared `after_a["theme"] == temp_theme`, which would have
    # false-positived here (the bug all three review layers caught).
    account_a = _FakeAccount(email=ACCOUNT_A_EMAIL, password="pw-a", theme="dark")
    account_b = _FakeAccount(email=ACCOUNT_B_EMAIL, password="pw-b", theme="light")
    client = _FakeAuthClient({"token-a": account_a, "token-b": account_b})

    result = _check_auth_theme_patch_scoped_to_caller(client, _HEADERS_A, _HEADERS_B)

    assert result.status == "pass"
    assert account_a.theme == "dark"  # untouched throughout
    assert account_b.theme == "light"  # reverted to its original value


def test_theme_check_flags_a_genuine_cross_tenant_change():
    account_a = _FakeAccount(email=ACCOUNT_A_EMAIL, password="pw-a", theme="light")
    account_b = _FakeAccount(email=ACCOUNT_B_EMAIL, password="pw-b", theme="light")
    accounts = {"token-a": account_a, "token-b": account_b}

    class _LeakyClient(_FakeAuthClient):
        def patch(self, path, json, headers):
            response = super().patch(path, json, headers)
            if path == "/auth/theme":
                # Simulate a scoping bug: every account's theme flips
                # together, not just the caller's own.
                for account in self._by_token.values():
                    account.theme = json["theme"]
            return response

    client = _LeakyClient(accounts)

    result = _check_auth_theme_patch_scoped_to_caller(client, _HEADERS_A, _HEADERS_B)

    assert result.status == "fail"
    assert "account A's theme changed" in result.detail


# ---------------------------------------------------------------------------
# _check_auth_password_change_scoped_to_caller -- review finding #2
# ---------------------------------------------------------------------------


def test_password_change_check_passes_when_account_a_password_is_untouched():
    account_a = _FakeAccount(email=ACCOUNT_A_EMAIL, password="qa1-real-pw")
    account_b = _FakeAccount(email=ACCOUNT_B_EMAIL, password="qa2-real-pw")
    client = _FakeAuthClient({"token-a": account_a, "token-b": account_b})

    result = _check_auth_password_change_scoped_to_caller(
        client, _HEADERS_A, _HEADERS_B, "qa1-real-pw", "qa2-real-pw"
    )

    assert result.status == "pass"
    assert account_a.password == "qa1-real-pw"
    assert account_b.password == "qa2-real-pw"  # reverted


def test_password_change_check_catches_a_leak_a_token_only_recheck_would_miss():
    # The exact failure class the fix closes (review finding #2): a
    # cross-tenant bug that silently overwrites account A's real stored
    # password. Re-checking A's already-issued JWT alone would still pass
    # here -- this codebase has no token-invalidation-on-password-change
    # mechanism at all -- so only a real login against the stored password
    # can observe it.
    account_a = _FakeAccount(email=ACCOUNT_A_EMAIL, password="qa1-real-pw")
    account_b = _FakeAccount(email=ACCOUNT_B_EMAIL, password="qa2-real-pw")
    accounts = {"token-a": account_a, "token-b": account_b}

    class _LeakyClient(_FakeAuthClient):
        def post(self, path, json, headers=None):
            response = super().post(path, json, headers)
            if path == "/auth/me/password" and response.status_code == 200:
                # Simulate the bug: B's own password change also
                # overwrites A's.
                account_a.password = json["new_password"]
            return response

    client = _LeakyClient(accounts)

    result = _check_auth_password_change_scoped_to_caller(
        client, _HEADERS_A, _HEADERS_B, "qa1-real-pw", "qa2-real-pw"
    )

    assert result.status == "fail"
    assert "account A's real password no longer works" in result.detail


def test_password_change_check_is_inconclusive_on_rate_limit_and_attempts_no_revert():
    # Second review round, finding #2: reverting unconditionally in
    # `finally` would send `current_password=_TEMP_PASSWORD` against a
    # password that was never actually changed if the initial call itself
    # hit the per-user rate limiter, itself fail, and raise
    # `IsolationProofError` claiming B's password might now be the temp
    # value -- a false alarm over completely unchanged state. Nothing
    # should be reverted here because nothing was changed.
    account_a = _FakeAccount(email=ACCOUNT_A_EMAIL, password="qa1-real-pw")
    account_b = _FakeAccount(email=ACCOUNT_B_EMAIL, password="qa2-real-pw")
    accounts = {"token-a": account_a, "token-b": account_b}

    class _RateLimitedClient(_FakeAuthClient):
        def post(self, path, json, headers=None):
            if path == "/auth/me/password":
                return _FakeResponse(429, {"detail": "Too many password change attempts."})
            return super().post(path, json, headers)

    client = _RateLimitedClient(accounts)

    result = _check_auth_password_change_scoped_to_caller(
        client, _HEADERS_A, _HEADERS_B, "qa1-real-pw", "qa2-real-pw"
    )

    assert result.status == "inconclusive"
    assert "rate-limited" in result.detail
    assert account_b.password == "qa2-real-pw"  # untouched -- no revert was ever attempted


# ---------------------------------------------------------------------------
# _check_chat_ask_no_leak / _check_kg_graph_no_leak positive control --
# second review round, finding #1: an absence-only check passes vacuously
# if retrieval/the graph returned nothing at all, which is not the same as
# isolation actually working.
# ---------------------------------------------------------------------------


class _FakeChatOrGraphClient:
    """Returns fixed response text per bearer token -- enough surface for
    both `_check_chat_ask_no_leak` (`.post`) and `_check_kg_graph_no_leak`
    (`.get`), since both only ever read `.status_code`/`.text`."""

    def __init__(self, text_by_token: dict[str, str], status_code: int = 200):
        self._text_by_token = text_by_token
        self._status_code = status_code

    def _response(self, headers):
        token = headers["Authorization"].removeprefix("Bearer ")
        return _FakeResponse(self._status_code, text=self._text_by_token[token])

    def post(self, path, json, headers):
        assert path == "/chat/ask"
        return self._response(headers)

    def get(self, path, headers):
        assert path == "/kg/graph"
        return self._response(headers)


def test_chat_check_is_inconclusive_when_the_callers_own_token_never_appears():
    # No leak either way, but "no leak found" here just means retrieval
    # returned an empty/refusal answer (AskResponse's no_documents/
    # empty_scope/refusal states) -- not that isolation was proven.
    client = _FakeChatOrGraphClient({"token-a": "I don't know based on the provided documents."})

    result = _check_chat_ask_no_leak(
        client, "chat_ask_no_leak_a_to_b", _HEADERS_A,
        own_token="OWN-TOKEN", other_token="OTHER-TOKEN", other_filename="other-fixture.md",
    )

    assert result.status == "inconclusive"


def test_chat_check_passes_when_own_token_present_and_no_cross_tenant_leak():
    client = _FakeChatOrGraphClient({"token-a": "The verification token is OWN-TOKEN."})

    result = _check_chat_ask_no_leak(
        client, "chat_ask_no_leak_a_to_b", _HEADERS_A,
        own_token="OWN-TOKEN", other_token="OTHER-TOKEN", other_filename="other-fixture.md",
    )

    assert result.status == "pass"


def test_chat_check_still_fails_on_a_leak_even_when_own_token_is_present():
    client = _FakeChatOrGraphClient(
        {"token-a": "The verification token is OWN-TOKEN, related to OTHER-TOKEN."}
    )

    result = _check_chat_ask_no_leak(
        client, "chat_ask_no_leak_a_to_b", _HEADERS_A,
        own_token="OWN-TOKEN", other_token="OTHER-TOKEN", other_filename="other-fixture.md",
    )

    assert result.status == "fail"


def test_kg_graph_check_is_inconclusive_when_the_callers_own_contact_never_appears():
    client = _FakeChatOrGraphClient({"token-a": "{}"})  # empty graph

    result = _check_kg_graph_no_leak(
        client, "kg_graph_no_leak_a_to_b", _HEADERS_A,
        own_contact="Own Contact", other_token="OTHER-TOKEN", other_contact="Other Contact",
    )

    assert result.status == "inconclusive"


def test_kg_graph_check_passes_when_own_contact_present_and_no_cross_tenant_leak():
    client = _FakeChatOrGraphClient({"token-a": '{"entities": ["Own Contact"]}'})

    result = _check_kg_graph_no_leak(
        client, "kg_graph_no_leak_a_to_b", _HEADERS_A,
        own_contact="Own Contact", other_token="OTHER-TOKEN", other_contact="Other Contact",
    )

    assert result.status == "pass"


def test_kg_graph_check_still_fails_on_a_leaked_contact_even_when_own_contact_is_present():
    client = _FakeChatOrGraphClient({"token-a": '{"entities": ["Own Contact", "Other Contact"]}'})

    result = _check_kg_graph_no_leak(
        client, "kg_graph_no_leak_a_to_b", _HEADERS_A,
        own_contact="Own Contact", other_token="OTHER-TOKEN", other_contact="Other Contact",
    )

    assert result.status == "fail"


# ---------------------------------------------------------------------------
# _check_forged_token_sweep vs. legitimate rate-limiting -- review finding #3
# ---------------------------------------------------------------------------


class _FakeSweepRoute:
    def __init__(self, path, methods):
        self.path = path
        self.methods = methods


class _FakeSweepClient:
    """Returns a fixed status per path, ignoring the token entirely --
    just enough surface for `_check_forged_token_sweep` (`.get` only,
    since every fake route below is a GET)."""

    def __init__(self, status_by_path: dict[str, int]):
        self._status_by_path = status_by_path

    def get(self, path, headers):
        return _FakeResponse(self._status_by_path[path])


def test_forged_token_sweep_does_not_treat_429_as_an_accepted_token():
    routes = [_FakeSweepRoute("/a", {"GET"}), _FakeSweepRoute("/b", {"GET"}), _FakeSweepRoute("/c", {"GET"})]
    client = _FakeSweepClient({"/a": 401, "/b": 429, "/c": 401})

    result = _check_forged_token_sweep(client, "sweep", "fake-token", routes)

    assert result.status == "pass"
    assert "rate-limited, not evaluated" in result.detail
    assert "/b" in result.detail


def test_forged_token_sweep_still_fails_on_a_genuinely_accepted_token():
    routes = [_FakeSweepRoute("/a", {"GET"}), _FakeSweepRoute("/b", {"GET"})]
    client = _FakeSweepClient({"/a": 401, "/b": 200})

    result = _check_forged_token_sweep(client, "sweep", "fake-token", routes)

    assert result.status == "fail"
    assert "accepted a forged token" in result.detail
    assert "/b -> 200" in result.detail


def test_forged_token_sweep_reports_rate_limits_distinctly_even_when_failing():
    # A 429 alongside a genuine accepted-token leak must not be swallowed
    # into either bucket -- both facts stay visible in the detail string.
    routes = [_FakeSweepRoute("/a", {"GET"}), _FakeSweepRoute("/b", {"GET"}), _FakeSweepRoute("/c", {"GET"})]
    client = _FakeSweepClient({"/a": 429, "/b": 200, "/c": 401})

    result = _check_forged_token_sweep(client, "sweep", "fake-token", routes)

    assert result.status == "fail"
    assert "/b -> 200" in result.detail
    assert "rate-limited, not evaluated" in result.detail
    assert "/a" in result.detail


# ---------------------------------------------------------------------------
# get_current_user really is the dependency the route enumeration looks for
# ---------------------------------------------------------------------------


def test_auth_me_route_dependency_tree_contains_get_current_user():
    (route,) = [r for r in _covered_routes(app) if r.path == "/auth/me" and "GET" in (r.methods or set())]
    assert _dependency_tree_contains(route.dependant, get_current_user) is True


# ---------------------------------------------------------------------------
# Report / pass-fail classification (spec Acceptance: names the failing
# check, states "0 leaks found" on a clean run, reports DELETE /auth/me
# distinctly as N/A)
# ---------------------------------------------------------------------------


def test_should_exit_nonzero_is_false_when_every_check_passes():
    results = [CheckResult(name="a", status="pass"), CheckResult(name="b", status="pass")]
    assert _should_exit_nonzero(results) is False


def test_should_exit_nonzero_is_true_when_any_check_fails():
    results = [CheckResult(name="a", status="pass"), CheckResult(name="b", status="fail", detail="leak!")]
    assert _should_exit_nonzero(results) is True


def test_should_exit_nonzero_is_true_when_any_check_is_inconclusive():
    # An inconclusive check is not proof of isolation -- the DoD gate must
    # not clear on a run where a positive control never fired, even though
    # "inconclusive" isn't literally a leak (the function's old name,
    # `_has_leaks`, claimed it was).
    results = [
        CheckResult(name="a", status="pass"),
        CheckResult(name="b", status="inconclusive", detail="unclear"),
    ]
    assert _should_exit_nonzero(results) is True


def test_print_report_states_zero_leaks_on_a_clean_run(capsys):
    from datetime import datetime, timezone

    results = [CheckResult(name="route_enumeration_auth_coverage", status="pass", detail="OK")]
    na_results = [NAResult(name="delete_auth_me_cross_tenant", detail="N/A by construction -- ...")]

    _print_report(results, na_results, started_at=datetime(2026, 8, 17, tzinfo=timezone.utc))

    out = capsys.readouterr().out
    assert "0 leaks found across 1 checks (1 reported N/A by construction)." in out
    assert "[PASS] route_enumeration_auth_coverage: OK" in out
    assert "[N/A ] delete_auth_me_cross_tenant" in out


def test_print_report_names_the_failing_check_and_does_not_say_zero_leaks(capsys):
    from datetime import datetime, timezone

    results = [
        CheckResult(name="documents_get_cross_tenant_blocked", status="pass", detail="OK"),
        CheckResult(
            name="chat_ask_no_leak_a_to_b",
            status="fail",
            detail="response contains the other account's token 'ISOLATION-TOKEN-BRAVO-9C1A47E2'",
        ),
    ]

    _print_report(results, [], started_at=datetime(2026, 8, 17, tzinfo=timezone.utc))

    out = capsys.readouterr().out
    assert "1 leak(s) found: chat_ask_no_leak_a_to_b" in out
    assert "[FAIL] chat_ask_no_leak_a_to_b:" in out
    assert "0 leaks found" not in out


def test_print_report_names_inconclusive_checks_distinctly_from_leaks(capsys):
    from datetime import datetime, timezone

    results = [
        CheckResult(name="documents_get_cross_tenant_blocked", status="pass", detail="OK"),
        CheckResult(
            name="chat_ask_no_leak_a_to_b",
            status="inconclusive",
            detail="own token never appeared -- retrieval returned nothing this run",
        ),
    ]

    _print_report(results, [], started_at=datetime(2026, 8, 17, tzinfo=timezone.utc))

    out = capsys.readouterr().out
    assert "[INCONCLUSIVE] chat_ask_no_leak_a_to_b:" in out
    assert "1 check(s) inconclusive" in out
    assert "chat_ask_no_leak_a_to_b" in out
    assert "0 leaks found" not in out
    assert "leak(s) found" not in out  # no genuine FAILs this run, only an inconclusive one
