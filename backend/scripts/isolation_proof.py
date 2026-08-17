"""Story 6.2: proves that no account can reach another account's data,
across every protected endpoint, driven through the real API layer.

Unlike `scripts/eval_harness.py` (Story 6.1, which deliberately calls
`chat.service.ask_question` directly, service-layer only), this script
drives the real FastAPI app in-process via `TestClient(app)` -- real
`Authorization: Bearer <jwt>` headers obtained from real `/auth/register`
+ `/auth/login` calls, zero `dependency_overrides`, real Postgres
(Neon)/Weaviate/Neo4j. Testing at the service layer (passing
`current_user` in as an argument) only proves the service+repo honor the
value handed to them -- it can't catch a route missing
`Depends(get_current_user)`, a route reading `user_id` from client input,
a forged/tampered token that still passes, or a new endpoint added
without scoping. Only driving the real HTTP layer catches those.

Never mocks Weaviate/Neo4j/Postgres/the LLM, and never uses the pytest
`client`/`db_session` fixtures (`backend/tests/conftest.py`) -- those are
SQLite-backed with ingestion stubbed, the opposite of what this proof
needs.

Covers, per the spec's Boundaries:
  - Route enumeration: every registered `APIRoute` outside the documented
    public allowlist must carry `get_current_user` in its dependency tree.
  - Cross-tenant blocked access: `auth/me` (get/patch/theme/password),
    `documents` (list/get/delete), `chat/ask`, `kg/graph`.
  - Bidirectional answer/graph blending: each account's fixture carries a
    unique token plus a same-named entity (`Meridian Fulcrum Holdings`) --
    stresses Neo4j's `user_id`-scoped entity merge specifically, since
    name-based dedup is the one thing that could blend two accounts'
    same-named entities if `user_id` filtering ever slipped.
  - Forged-token perimeter sweep: every enumerated protected route must
    reject both a wrong-signature token (fails inside
    `decode_access_token`'s `except jwt.PyJWTError` branch) and a
    validly-signed token for a nonexistent user (passes signature
    verification, fails at `repository.get_user_by_id`) -- two genuinely
    distinct code branches, not the same rejection tested twice.
  - `DELETE /auth/me` is reported "N/A by construction", not covered/not
    covered -- it takes no target parameter, so there is no cross-tenant
    surface to prove there.

A detected leak is never fixed inline here -- every check keeps running so
the report is complete, and the script exits non-zero listing exactly
which check(s) failed. A human decides how to proceed from there (spec's
Ask First note).

Account A is the existing real QA account (`essinkabg@gmail.com`).
Account B is a second, permanent, git-documented QA account (fixed email
`essinkabg+qa2@gmail.com`). Both need a real password to log in through
`/auth/login`; Account B's is `ISOLATION_QA2_PASSWORD` (spec's own name).
The spec is silent on how Account A authenticates, since every other
story's scripts only ever needed A by direct DB lookup, never a real
login -- this script is the first to actually need A's password, so it
introduces `ISOLATION_QA1_PASSWORD` as the symmetric env var, following
the same naming convention. Registration is idempotent for both accounts
(`POST /auth/register`, fall back to `/auth/login` on `409`) -- neither
account is ever recreated per run, and Account B's happy-path self-delete
is never exercised (spec's Never clause).

Usage (run from `backend/`, same convention as `scripts/eval_harness.py`):

    python -m scripts.isolation_proof
"""

import argparse
import logging
import os
import pathlib
import re
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.auth import service as auth_service
from app.auth.dependencies import get_current_user
from app.main import app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ACCOUNT_A_EMAIL = "essinkabg@gmail.com"
ACCOUNT_A_FULL_NAME = "GraphMind QA"

ACCOUNT_B_EMAIL = "essinkabg+qa2@gmail.com"
ACCOUNT_B_FULL_NAME = "GraphMind QA -- Isolation Account B"

_SCRIPT_DIR = pathlib.Path(__file__).parent
FIXTURES_DIR = _SCRIPT_DIR / "isolation_fixtures"
FIXTURE_A_PATH = FIXTURES_DIR / "isolation_fixture_account_a.md"
FIXTURE_B_PATH = FIXTURES_DIR / "isolation_fixture_account_b.md"

# Must match the fixture files' own content exactly -- these are what every
# leak assertion below searches for in the *other* account's responses.
ACCOUNT_A_TOKEN = "ISOLATION-TOKEN-ALPHA-6F3D9C21"
ACCOUNT_B_TOKEN = "ISOLATION-TOKEN-BRAVO-9C1A47E2"
SHARED_ENTITY_NAME = "Meridian Fulcrum Holdings"
ACCOUNT_A_CONTACT_NAME = "Talia Voss"
ACCOUNT_B_CONTACT_NAME = "Denny Okafor"

_ASK_QUESTION = (
    f"What are the contract terms, verification token, and contact for the "
    f"{SHARED_ENTITY_NAME} vendor agreement?"
)

# The DoD gate this script exists to prove -- checked up front with one
# clear message rather than each register/login/upload call failing with
# its own scattered error partway through the run. Mirrors
# eval_harness.py's REQUIRED_ENV_VARS/_validate_env pattern.
REQUIRED_ENV_VARS = [
    "DATABASE_URL",
    "JWT_SECRET",
    "WEAVIATE_URL",
    "WEAVIATE_API_KEY",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "OPENROUTER_API_KEY",
    # Account A's real password -- see this module's docstring for why this
    # script (unlike eval_harness.py) needs it at all: it's the first
    # script that authenticates via a real /auth/login rather than a
    # direct DB lookup.
    "ISOLATION_QA1_PASSWORD",
    # Spec's own name for Account B's password.
    "ISOLATION_QA2_PASSWORD",
]

_POLL_INTERVAL_SECONDS = 3.0
_POLL_TIMEOUT_SECONDS = 300.0

_READY_STATUS = "Ready"
_FAILED_STATUS = "Failed"

# The spec's documented public allowlist -- every other `APIRoute` must
# carry `get_current_user` in its dependency tree. `/docs`/`/openapi.json`
# aren't `APIRoute` instances in this FastAPI version (plain `Route`s), so
# they're never actually checked below, but are kept here per the spec's
# literal text and as a defensive no-op if a future FastAPI version ever
# does wrap them as `APIRoute`.
PUBLIC_ALLOWLIST_PATHS = frozenset(
    {"/auth/register", "/auth/login", "/health", "/docs", "/openapi.json"}
)

# `_covered_routes` ducktypes on FastAPI 0.141.1's private
# `_IncludedRouter.original_router` (see `_iter_effective_routes`'s
# docstring) to expand `app.routes` -- a future FastAPI version that stops
# using that wrapper would make `_iter_effective_routes` silently degrade
# to yielding routes as-is, which could shrink `covered_routes` down to
# almost nothing (just `/health`) without raising anything. This is the
# known-route-count floor (today's real 11: auth/me GET+PATCH+DELETE,
# auth/theme PATCH, auth/me/password POST, documents GET+POST,
# documents/{id} GET+DELETE, chat/ask POST, kg/graph GET) that `_run()`
# asserts against right after building `covered_routes` -- a silently
# near-empty check set must abort loudly, never print a misleadingly clean
# "0 leaks found" (review finding).
_MIN_EXPECTED_COVERED_ROUTES = 11

_TEMP_FULL_NAME_SUFFIX = " (isolation-check)"
_TEMP_PASSWORD = "TempIsolationCheck!2026Q"  # noqa: S105 -- reverted immediately, never persisted

_PATH_PARAM_RE = re.compile(r"\{[^}]+\}")


class IsolationProofError(Exception):
    """An abort condition: missing env vars, a fixture that failed/is
    stuck, an unexpected non-2xx/404 during account setup, or a failed
    attempt to revert a mutating check back to its original state. Never
    raised for a detected *leak* -- those are recorded as failing
    `CheckResult`s so the rest of the report still runs (spec's Ask First
    note: report a leak, don't abort mid-proof over it)."""


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def _validate_env() -> None:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name, "").strip()]
    if missing:
        raise IsolationProofError(
            "Missing required environment variable(s): "
            f"{', '.join(missing)}. See backend/.env.example. This proof runs against real "
            "Weaviate/Neo4j/OpenRouter/Postgres by design -- there is no mocked fallback."
        )


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Route enumeration (spec Boundaries row 1)
# ---------------------------------------------------------------------------


def _iter_effective_routes(routes):
    """Recursively expands `_IncludedRouter` wrappers.

    This FastAPI version (0.141.1) wraps every `include_router`ed router in
    a lazy `_IncludedRouter` rather than flattening it into `app.routes`
    directly -- a naive `for route in app.routes` sees only `/health` plus
    the doc routes, silently missing every auth/documents/chat/kg route.
    Ducktyped on `original_router` (rather than importing the private
    `_IncludedRouter` class) so this degrades gracefully -- yielding the
    route as-is -- on a FastAPI version that flattens routes eagerly
    instead.
    """
    for route in routes:
        original_router = getattr(route, "original_router", None)
        if original_router is not None:
            yield from _iter_effective_routes(original_router.routes)
        else:
            yield route


def _dependency_tree_contains(dependant, target) -> bool:
    """Recursively searches `dependant.dependencies` (FastAPI's own
    resolved-dependency tree, built once at route-registration time) for
    `target` (`get_current_user`). Checks `dependant.call` at every level,
    not just the top -- `get_current_user` itself is usually a
    sub-dependency of the route's own `Depends(...)` params, several
    levels deep once `HTTPBearer`/`get_db_session` are counted too."""
    if dependant.call is target:
        return True
    return any(_dependency_tree_contains(sub, target) for sub in dependant.dependencies)


def _covered_routes(app) -> list[APIRoute]:
    """Every `APIRoute` outside the public allowlist -- the set the
    forged-token sweep runs against, and the set the route-enumeration
    check verifies all carry `get_current_user`."""
    return [
        route
        for route in _iter_effective_routes(app.routes)
        if isinstance(route, APIRoute) and route.path not in PUBLIC_ALLOWLIST_PATHS
    ]


def _find_unscoped_routes(app) -> list[tuple[str, str]]:
    """Returns `(method, path)` for every covered route missing
    `get_current_user` in its dependency tree. Empty means every protected
    route is genuinely scoped -- the route-enumeration check's whole
    point, per the spec: this is what catches a future endpoint added
    without `Depends(get_current_user)`, which no cross-tenant behavioral
    test below could ever catch (there'd be nothing IDOR-shaped to
    exercise if the route just... has no auth at all)."""
    unscoped = []
    for route in _covered_routes(app):
        if not _dependency_tree_contains(route.dependant, get_current_user):
            methods = sorted((route.methods or set()) - {"HEAD", "OPTIONS"})
            unscoped.append((",".join(methods) or "?", route.path))
    return unscoped


# ---------------------------------------------------------------------------
# Forged-token perimeter sweep (spec Boundaries row 5)
# ---------------------------------------------------------------------------


def _build_wrong_signature_token() -> str:
    """A token signed with a secret the app never reads -- must fail
    inside `decode_access_token`'s `except jwt.PyJWTError` branch, before
    `repository.get_user_by_id` (or any DB call) ever runs."""
    now = datetime.now(timezone.utc)
    payload = {"sub": str(uuid.uuid4()), "iat": now, "exp": now + timedelta(minutes=60)}
    return jwt.encode(
        payload, "deliberately-wrong-secret-for-isolation-proof", algorithm=auth_service.JWT_ALGORITHM
    )


def _build_unknown_user_token() -> str:
    """A genuinely validly-signed token (the app's own `JWT_SECRET`, via
    the real `create_access_token`) for a `sub` no user will ever have --
    signature verification passes, so the 401 must come from
    `get_user_by_id` returning `None`. Deliberately built via the same
    function `POST /auth/login` uses, not a hand-rolled `jwt.encode` call
    with a copied secret -- that's what makes this genuinely a different
    branch from the wrong-signature token above, not the same rejection
    tested twice under a different name."""
    return auth_service.create_access_token(uuid.uuid4())


def _primary_method(route: APIRoute) -> str | None:
    methods = (route.methods or set()) - {"HEAD", "OPTIONS"}
    if not methods:
        return None
    for candidate in ("GET", "POST", "PATCH", "PUT", "DELETE"):
        if candidate in methods:
            return candidate
    return sorted(methods)[0]


def _concrete_path(route: APIRoute) -> str:
    """Substitutes a syntactically-valid random UUID for every `{param}`
    in the route's path template -- e.g. `/documents/{document_id}` ->
    `/documents/<uuid>`. The actual value never matters for the
    forged-token sweep: `get_current_user` rejects both forged tokens
    during dependency resolution, before the path param or body is ever
    read by the route body (verified empirically -- an invalid/missing
    body or an unparsable path param still comes back 401, not 422, when
    the token itself is what's invalid)."""
    return _PATH_PARAM_RE.sub(lambda _: str(uuid.uuid4()), route.path)


def _send_forged_request(client: TestClient, method: str, path: str, token: str):
    headers = _auth_header(token)
    if method == "GET":
        return client.get(path, headers=headers)
    if method == "DELETE":
        return client.delete(path, headers=headers)
    if method in ("POST", "PATCH", "PUT"):
        return client.request(method, path, json={}, headers=headers)
    raise IsolationProofError(f"Unhandled HTTP method {method!r} while sweeping {path!r}.")


def _check_forged_token_sweep(
    client: TestClient, name: str, token: str, covered_routes: list[APIRoute]
) -> "CheckResult":
    accepted: list[str] = []
    rate_limited: list[str] = []
    for route in covered_routes:
        method = _primary_method(route)
        if method is None:
            continue
        response = _send_forged_request(client, method, _concrete_path(route), token)
        if response.status_code == 401:
            continue
        if response.status_code == 429:
            # A route's own legitimate rate limiter, not a security leak --
            # the request was still rejected, just for a different (also
            # correct) reason than the forged token itself. Reported
            # distinctly rather than folded into either "OK" or "accepted a
            # forged token" (review finding): treating 429 as a leak would
            # false-positive whenever an earlier check in the same run
            # already spent part of that route's window; treating it
            # silently as "OK" would hide that this route genuinely wasn't
            # evaluated against the forged token this run.
            rate_limited.append(f"{method} {route.path}")
            continue
        accepted.append(f"{method} {route.path} -> {response.status_code}")

    rate_limited_note = (
        f"; {len(rate_limited)} route(s) rate-limited, not evaluated: {', '.join(rate_limited)}"
        if rate_limited
        else ""
    )
    if accepted:
        return _fail(name, "accepted a forged token: " + "; ".join(accepted) + rate_limited_note)
    evaluated = len(covered_routes) - len(rate_limited)
    return _pass(name, f"OK (401 on {evaluated} of {len(covered_routes)} covered routes){rate_limited_note}")


# ---------------------------------------------------------------------------
# Account setup / fixture ingestion
# ---------------------------------------------------------------------------


def _register_or_login(client: TestClient, *, full_name: str, email: str, password: str) -> str:
    """Idempotent per spec Boundaries: `POST /auth/register`, falling back
    to `/auth/login` on `409` -- never fails because the account already
    exists, never recreates it. Login always runs regardless of the
    register outcome, since `RegisterResponse` carries no access token."""
    register_response = client.post(
        "/auth/register", json={"full_name": full_name, "email": email, "password": password}
    )
    if register_response.status_code not in (201, 409):
        raise IsolationProofError(
            f"Unexpected status registering {email!r}: {register_response.status_code} "
            f"{register_response.text}"
        )
    login_response = client.post("/auth/login", json={"email": email, "password": password})
    if login_response.status_code != 200:
        raise IsolationProofError(
            f"Login failed for {email!r}: {login_response.status_code} {login_response.text}"
        )
    return login_response.json()["access_token"]


def _upload_fixture(client: TestClient, token: str, fixture_path: pathlib.Path) -> dict:
    content = fixture_path.read_bytes()
    response = client.post(
        "/documents",
        files={"file": (fixture_path.name, content, "text/markdown")},
        headers=_auth_header(token),
    )
    if response.status_code not in (200, 201):
        raise IsolationProofError(
            f"Uploading fixture {fixture_path.name!r} failed unexpectedly: "
            f"{response.status_code} {response.text}"
        )
    body = response.json()
    if response.status_code == 201:
        outcome = "created"
    elif body.get("is_duplicate"):
        outcome = "duplicate"
    else:
        outcome = "reingested"
    logger.info("Fixture %s: upload outcome=%s (document_id=%s)", fixture_path.name, outcome, body["id"])
    return body


def _poll_document_ready(
    client: TestClient,
    headers: dict[str, str],
    document_id: str,
    *,
    timeout: float = _POLL_TIMEOUT_SECONDS,
    interval: float = _POLL_INTERVAL_SECONDS,
    sleep=time.sleep,
    now=time.monotonic,
) -> dict:
    """Re-fetches `document_id` via `GET /documents/{id}` until its status
    is `Ready`/`Failed` or `timeout` elapses.

    `TestClient` runs `BackgroundTasks` synchronously to completion before
    `client.post(...)` returns (see `conftest.py`'s comment on the same
    behavior), so a fresh ("created"/"reingested") fixture is normally
    already terminal on this function's very first iteration -- this isn't
    a real wait loop in the common case, just the one clean way to read
    the row's current status regardless of which of the three upload
    outcomes produced it (the upload response body itself was serialized
    *before* the background task ran, so it can't be trusted for this).
    """
    deadline = now() + timeout
    while True:
        response = client.get(f"/documents/{document_id}", headers=headers)
        if response.status_code != 200:
            raise IsolationProofError(
                f"GET /documents/{document_id} failed while polling for Ready: "
                f"{response.status_code} {response.text}"
            )
        body = response.json()
        if body["status"] in (_READY_STATUS, _FAILED_STATUS):
            return body
        if now() >= deadline:
            raise IsolationProofError(
                f"Timed out after {timeout}s waiting for fixture document {document_id} to leave "
                f"status={body['status']!r}. Resolve manually before re-running."
            )
        sleep(interval)


def _ingest_fixture(client: TestClient, token: str, fixture_path: pathlib.Path) -> dict:
    headers = _auth_header(token)
    body = _upload_fixture(client, token, fixture_path)
    document = _poll_document_ready(client, headers, body["id"])
    if document["status"] == _FAILED_STATUS:
        raise IsolationProofError(
            f"Fixture {fixture_path.name!r} (document_id={document['id']}) failed ingestion: "
            f"{document.get('failed_reason')}"
        )
    return document


# ---------------------------------------------------------------------------
# Check result plumbing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Literal["pass", "fail"]
    detail: str = ""


@dataclass(frozen=True)
class NAResult:
    name: str
    detail: str


def _pass(name: str, detail: str = "OK") -> CheckResult:
    return CheckResult(name=name, status="pass", detail=detail)


def _fail(name: str, detail: str) -> CheckResult:
    return CheckResult(name=name, status="fail", detail=detail)


def _has_leaks(results: list[CheckResult]) -> bool:
    return any(r.status == "fail" for r in results)


# ---------------------------------------------------------------------------
# Cross-tenant checks: auth/me family (spec Boundaries row 2, no target
# param on any of these -- see the module docstring's naming-gap note.
# `/auth/me` GET is read-only; PATCH/theme/password mutate account B and
# always revert to B's original value in a `finally`, verifying account A
# is untouched in between.)
# ---------------------------------------------------------------------------


def _check_auth_me_identity_isolation(
    client: TestClient, headers_a: dict, headers_b: dict
) -> CheckResult:
    name = "auth_me_get_identity_isolation"
    resp_a = client.get("/auth/me", headers=headers_a)
    resp_b = client.get("/auth/me", headers=headers_b)
    if resp_a.status_code != 200 or resp_b.status_code != 200:
        return _fail(name, f"unexpected status: A={resp_a.status_code} B={resp_b.status_code}")
    body_a, body_b = resp_a.json(), resp_b.json()
    leaks = []
    if body_a["email"] != ACCOUNT_A_EMAIL:
        leaks.append(f"A's /auth/me returned email {body_a['email']!r}, expected {ACCOUNT_A_EMAIL!r}")
    if body_b["email"] != ACCOUNT_B_EMAIL:
        leaks.append(f"B's /auth/me returned email {body_b['email']!r}, expected {ACCOUNT_B_EMAIL!r}")
    if body_a["id"] == body_b["id"]:
        leaks.append("A and B resolved to the same user id")
    if ACCOUNT_B_EMAIL in resp_a.text:
        leaks.append("B's email appeared in A's /auth/me response")
    if ACCOUNT_A_EMAIL in resp_b.text:
        leaks.append("A's email appeared in B's /auth/me response")
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


def _check_auth_me_patch_scoped_to_caller(
    client: TestClient, headers_a: dict, headers_b: dict
) -> CheckResult:
    name = "auth_me_patch_scoped_to_caller"
    original_b = client.get("/auth/me", headers=headers_b).json()
    original_full_name = original_b["full_name"]
    temp_name = f"{original_full_name}{_TEMP_FULL_NAME_SUFFIX}"
    leaks: list[str] = []
    try:
        patch_resp = client.patch("/auth/me", json={"full_name": temp_name}, headers=headers_b)
        if patch_resp.status_code != 200:
            leaks.append(f"PATCH /auth/me as B returned {patch_resp.status_code}, expected 200")
        else:
            after_b = client.get("/auth/me", headers=headers_b).json()
            if after_b["full_name"] != temp_name:
                leaks.append("B's own PATCH /auth/me did not apply to B's own account")
            after_a = client.get("/auth/me", headers=headers_a).json()
            if after_a["full_name"] == temp_name or after_a["email"] != ACCOUNT_A_EMAIL:
                leaks.append("account A's profile changed after B's PATCH /auth/me")
    finally:
        revert_resp = client.patch("/auth/me", json={"full_name": original_full_name}, headers=headers_b)
        if revert_resp.status_code != 200:
            raise IsolationProofError(
                f"Failed to revert account B's full_name back to {original_full_name!r} after the "
                f"isolation check ({revert_resp.status_code}) -- B's profile may now be left mutated. "
                "Fix manually before re-running."
            )
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


def _check_auth_theme_patch_scoped_to_caller(
    client: TestClient, headers_a: dict, headers_b: dict
) -> CheckResult:
    name = "auth_theme_patch_scoped_to_caller"
    original_b = client.get("/auth/me", headers=headers_b).json()
    original_theme = original_b["theme"]
    temp_theme = "dark" if original_theme != "dark" else "light"
    # Captured *before* B's PATCH -- theme only has two values, so if A's
    # pre-existing theme already happens to equal `temp_theme`, comparing
    # only against `after_a` would false-positive a "leak" on a run where
    # nothing actually changed (review finding: all three review layers
    # caught this independently).
    original_a_theme = client.get("/auth/me", headers=headers_a).json()["theme"]
    leaks: list[str] = []
    try:
        patch_resp = client.patch("/auth/theme", json={"theme": temp_theme}, headers=headers_b)
        if patch_resp.status_code != 200:
            leaks.append(f"PATCH /auth/theme as B returned {patch_resp.status_code}, expected 200")
        else:
            after_a = client.get("/auth/me", headers=headers_a).json()
            if (
                after_a["theme"] == temp_theme
                and original_a_theme != temp_theme
                and after_a["email"] == ACCOUNT_A_EMAIL
            ):
                # Only a real leak if A's theme actually flipped to match B's
                # new value -- a coincidental pre-existing match (A was
                # already on `temp_theme` before B's PATCH ran) is not
                # itself evidence of a leak, so this only fires when B's
                # temp value genuinely changed A's theme too.
                leaks.append("account A's theme changed after B's PATCH /auth/theme")
    finally:
        revert_resp = client.patch("/auth/theme", json={"theme": original_theme}, headers=headers_b)
        if revert_resp.status_code != 200:
            raise IsolationProofError(
                f"Failed to revert account B's theme back to {original_theme!r} after the isolation "
                f"check ({revert_resp.status_code}) -- B's theme may now be left mutated. Fix manually "
                "before re-running."
            )
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


def _check_auth_password_change_scoped_to_caller(
    client: TestClient, headers_a: dict, headers_b: dict, qa1_password: str, qa2_password: str
) -> CheckResult:
    """Exercises `POST /auth/me/password` as account B only -- never
    against account A's real password (spec's Never clause protects A more
    broadly; this mirrors that caution even where not strictly required).

    Proves the change is scoped to B's own account by attempting a real
    `POST /auth/login` as account A with `qa1_password` afterward -- not
    just re-using A's already-issued JWT. Per `get_current_user`'s real
    implementation (`app/auth/dependencies.py`), a JWT's validity depends
    only on its signature/expiry plus `get_user_by_id`, never on
    `password_hash` -- and this codebase has no token-invalidation-on-
    password-change mechanism at all (a known, recorded gap -- see
    `deferred-work.md`'s Story 5.1 entry). So re-checking the existing
    token alone would still report "pass" even if a cross-tenant bug
    silently overwrote account A's real stored password, which is exactly
    the failure class this check exists to catch (review finding) -- only
    a real login against the stored `password_hash` actually observes
    that.

    Always reverts B's password back to `qa2_password` in a `finally`,
    since B is a permanent fixture whose password must stay the
    `ISOLATION_QA2_PASSWORD` value across runs -- a failed revert raises
    (rather than being folded into the check result) because it leaves
    real, persistent broken state that needs immediate human attention,
    not just a line in a report.
    """
    name = "auth_password_change_scoped_to_caller"
    leaks: list[str] = []
    try:
        change_resp = client.post(
            "/auth/me/password",
            json={"current_password": qa2_password, "new_password": _TEMP_PASSWORD},
            headers=headers_b,
        )
        if change_resp.status_code != 200:
            leaks.append(
                f"POST /auth/me/password as B returned {change_resp.status_code}, expected 200"
            )
        else:
            # A's real stored password must still be qa1_password -- the
            # only thing that actually observes whether B's change touched
            # A's password_hash, since A's already-issued token would keep
            # working regardless (JWTs aren't invalidated by a password
            # change in this codebase).
            login_a = client.post(
                "/auth/login", json={"email": ACCOUNT_A_EMAIL, "password": qa1_password}
            )
            # `LoginResponse` carries no email field, but `POST /auth/login`
            # only ever returns 200 when email+password together match one
            # real account (`authenticate_user`'s single generic 401
            # otherwise) -- so a 200 here already proves qa1_password still
            # authenticates account A specifically.
            if login_a.status_code != 200:
                leaks.append(
                    "account A's real password no longer works after B's password change "
                    f"(login status={login_a.status_code})"
                )
    finally:
        revert_resp = client.post(
            "/auth/me/password",
            json={"current_password": _TEMP_PASSWORD, "new_password": qa2_password},
            headers=headers_b,
        )
        if revert_resp.status_code != 200:
            raise IsolationProofError(
                f"Failed to revert account B's password back to ISOLATION_QA2_PASSWORD after the "
                f"isolation check ({revert_resp.status_code}) -- B's real password may now be "
                f"{_TEMP_PASSWORD!r} instead of the documented value. Fix manually (log in with the "
                "temp password and change it back) before re-running."
            )
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


# ---------------------------------------------------------------------------
# Cross-tenant checks: documents (spec Boundaries row 2)
# ---------------------------------------------------------------------------


def _check_documents_list_no_leak(
    client: TestClient, headers_a: dict, headers_b: dict, doc_a_id: str, doc_b_id: str
) -> CheckResult:
    name = "documents_list_no_cross_tenant_leak"
    resp_a = client.get("/documents", headers=headers_a)
    resp_b = client.get("/documents", headers=headers_b)
    if resp_a.status_code != 200 or resp_b.status_code != 200:
        return _fail(name, f"unexpected status: A={resp_a.status_code} B={resp_b.status_code}")
    ids_a = {d["id"] for d in resp_a.json()}
    ids_b = {d["id"] for d in resp_b.json()}
    leaks = []
    if doc_b_id in ids_a:
        leaks.append("A's document list contains B's fixture document id")
    if doc_a_id in ids_b:
        leaks.append("B's document list contains A's fixture document id")
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


def _check_documents_get_cross_tenant_blocked(
    client: TestClient, headers_a: dict, headers_b: dict, doc_a: dict, doc_b: dict
) -> CheckResult:
    name = "documents_get_cross_tenant_blocked"
    leaks = []
    resp_a_to_b = client.get(f"/documents/{doc_b['id']}", headers=headers_a)
    if resp_a_to_b.status_code != 404:
        leaks.append(f"A GET B's document returned {resp_a_to_b.status_code}, expected 404")
    elif doc_b["filename"] in resp_a_to_b.text:
        leaks.append("A's 404 response for B's document leaked B's filename")
    resp_b_to_a = client.get(f"/documents/{doc_a['id']}", headers=headers_b)
    if resp_b_to_a.status_code != 404:
        leaks.append(f"B GET A's document returned {resp_b_to_a.status_code}, expected 404")
    elif doc_a["filename"] in resp_b_to_a.text:
        leaks.append("B's 404 response for A's document leaked A's filename")
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


def _check_documents_delete_cross_tenant_blocked(
    client: TestClient, headers_a: dict, headers_b: dict, doc_a: dict, doc_b: dict
) -> CheckResult:
    name = "documents_delete_cross_tenant_blocked"
    leaks = []
    resp_a_to_b = client.delete(f"/documents/{doc_b['id']}", headers=headers_a)
    if resp_a_to_b.status_code != 404:
        leaks.append(f"A DELETE B's document returned {resp_a_to_b.status_code}, expected 404")
    verify_b = client.get(f"/documents/{doc_b['id']}", headers=headers_b)
    if verify_b.status_code != 200:
        leaks.append(
            f"B's fixture document is gone after A's blocked delete attempt "
            f"(status={verify_b.status_code}) -- the delete leaked through"
        )
    resp_b_to_a = client.delete(f"/documents/{doc_a['id']}", headers=headers_b)
    if resp_b_to_a.status_code != 404:
        leaks.append(f"B DELETE A's document returned {resp_b_to_a.status_code}, expected 404")
    verify_a = client.get(f"/documents/{doc_a['id']}", headers=headers_a)
    if verify_a.status_code != 200:
        leaks.append(
            f"A's fixture document is gone after B's blocked delete attempt "
            f"(status={verify_a.status_code}) -- the delete leaked through"
        )
    return CheckResult(name=name, status="pass" if not leaks else "fail", detail="; ".join(leaks) or "OK")


# ---------------------------------------------------------------------------
# Bidirectional blending checks: chat/ask and kg/graph (spec Boundaries
# rows 6-7)
# ---------------------------------------------------------------------------


def _check_chat_ask_no_leak(
    client: TestClient, name: str, headers: dict, *, other_token: str, other_filename: str
) -> CheckResult:
    response = client.post("/chat/ask", json={"question": _ASK_QUESTION}, headers=headers)
    if response.status_code != 200:
        return _fail(name, f"POST /chat/ask returned {response.status_code}: {response.text[:300]}")
    blob = response.text
    leaks = []
    if other_token in blob:
        leaks.append(f"response contains the other account's token {other_token!r}")
    if other_filename in blob:
        leaks.append(f"response cites the other account's fixture filename {other_filename!r}")
    return CheckResult(
        name=name,
        status="pass" if not leaks else "fail",
        detail="; ".join(leaks) or "OK (no cross-tenant token/filename found)",
    )


def _check_kg_graph_no_leak(
    client: TestClient, name: str, headers: dict, *, other_token: str, other_contact: str
) -> CheckResult:
    response = client.get("/kg/graph", headers=headers)
    if response.status_code != 200:
        return _fail(name, f"GET /kg/graph returned {response.status_code}: {response.text[:300]}")
    blob = response.text
    leaks = []
    if other_token in blob:
        leaks.append(f"graph response contains the other account's token {other_token!r}")
    if other_contact in blob:
        leaks.append(
            f"graph response contains the other account's contact name {other_contact!r} -- "
            "possible Neo4j user_id-scoping leak on the shared-name entity"
        )
    return CheckResult(
        name=name,
        status="pass" if not leaks else "fail",
        detail="; ".join(leaks) or "OK (no cross-tenant token/entity blending found)",
    )


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def _print_report(
    results: list[CheckResult], na_results: list[NAResult], *, started_at: datetime
) -> None:
    print("=" * 78)
    print("GraphMind Cross-Tenant Isolation Proof -- Story 6.2")
    print(f"Run started:  {started_at.isoformat()}")
    print(f"Account A:    {ACCOUNT_A_EMAIL}")
    print(f"Account B:    {ACCOUNT_B_EMAIL}")
    print("=" * 78)

    for result in results:
        status_label = "PASS" if result.status == "pass" else "FAIL"
        print(f"[{status_label}] {result.name}: {result.detail}")

    for na in na_results:
        print(f"[N/A ] {na.name}: {na.detail}")

    failing = [r for r in results if r.status == "fail"]
    print("=" * 78)
    if failing:
        print(f"{len(failing)} leak(s) found: {', '.join(r.name for r in failing)}")
    else:
        print(
            f"0 leaks found across {len(results)} checks "
            f"({len(na_results)} reported N/A by construction)."
        )
    print("=" * 78)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _run() -> int:
    started_at = datetime.now(timezone.utc)
    _validate_env()

    client = TestClient(app)

    qa1_password = os.environ["ISOLATION_QA1_PASSWORD"]
    qa2_password = os.environ["ISOLATION_QA2_PASSWORD"]

    token_a = _register_or_login(
        client, full_name=ACCOUNT_A_FULL_NAME, email=ACCOUNT_A_EMAIL, password=qa1_password
    )
    token_b = _register_or_login(
        client, full_name=ACCOUNT_B_FULL_NAME, email=ACCOUNT_B_EMAIL, password=qa2_password
    )
    headers_a, headers_b = _auth_header(token_a), _auth_header(token_b)

    logger.info("Ingesting fixture for account A...")
    doc_a = _ingest_fixture(client, token_a, FIXTURE_A_PATH)
    logger.info("Ingesting fixture for account B...")
    doc_b = _ingest_fixture(client, token_b, FIXTURE_B_PATH)

    results: list[CheckResult] = []

    unscoped = _find_unscoped_routes(app)
    if unscoped:
        detail = "; ".join(f"{method} {path}" for method, path in unscoped)
        results.append(_fail("route_enumeration_auth_coverage", f"unscoped route(s) found: {detail}"))
    else:
        results.append(_pass("route_enumeration_auth_coverage", "OK (every non-public route requires get_current_user)"))

    results.append(_check_auth_me_identity_isolation(client, headers_a, headers_b))
    results.append(_check_auth_me_patch_scoped_to_caller(client, headers_a, headers_b))
    results.append(_check_auth_theme_patch_scoped_to_caller(client, headers_a, headers_b))
    results.append(
        _check_auth_password_change_scoped_to_caller(
            client, headers_a, headers_b, qa1_password, qa2_password
        )
    )

    results.append(_check_documents_list_no_leak(client, headers_a, headers_b, doc_a["id"], doc_b["id"]))
    results.append(_check_documents_get_cross_tenant_blocked(client, headers_a, headers_b, doc_a, doc_b))
    results.append(
        _check_documents_delete_cross_tenant_blocked(client, headers_a, headers_b, doc_a, doc_b)
    )

    results.append(
        _check_chat_ask_no_leak(
            client, "chat_ask_no_leak_a_to_b", headers_a,
            other_token=ACCOUNT_B_TOKEN, other_filename=doc_b["filename"],
        )
    )
    results.append(
        _check_chat_ask_no_leak(
            client, "chat_ask_no_leak_b_to_a", headers_b,
            other_token=ACCOUNT_A_TOKEN, other_filename=doc_a["filename"],
        )
    )

    results.append(
        _check_kg_graph_no_leak(
            client, "kg_graph_no_leak_a_to_b", headers_a,
            other_token=ACCOUNT_B_TOKEN, other_contact=ACCOUNT_B_CONTACT_NAME,
        )
    )
    results.append(
        _check_kg_graph_no_leak(
            client, "kg_graph_no_leak_b_to_a", headers_b,
            other_token=ACCOUNT_A_TOKEN, other_contact=ACCOUNT_A_CONTACT_NAME,
        )
    )

    covered_routes = _covered_routes(app)
    if len(covered_routes) < _MIN_EXPECTED_COVERED_ROUTES:
        raise IsolationProofError(
            f"Route enumeration found only {len(covered_routes)} covered route(s), fewer than the "
            f"expected minimum of {_MIN_EXPECTED_COVERED_ROUTES} -- _iter_effective_routes' "
            "_IncludedRouter ducktyping may have silently stopped matching this FastAPI version's "
            "route tree, which would make the forged-token sweep (and the whole route-enumeration "
            "check) evaluate a near-empty, meaningless set of routes rather than the real app. "
            "Aborting rather than risk printing a misleadingly clean report."
        )
    results.append(
        _check_forged_token_sweep(
            client, "forged_token_wrong_signature_sweep", _build_wrong_signature_token(), covered_routes
        )
    )
    results.append(
        _check_forged_token_sweep(
            client, "forged_token_unknown_user_sweep", _build_unknown_user_token(), covered_routes
        )
    )

    na_results = [
        NAResult(
            name="delete_auth_me_cross_tenant",
            detail=(
                "N/A by construction -- DELETE /auth/me takes no target parameter, so a caller can "
                "only ever delete the account named by their own valid token. There is no "
                "cross-tenant surface to prove, and account B's happy-path self-delete is never "
                "exercised (spec's Never clause)."
            ),
        )
    ]

    _print_report(results, na_results, started_at=started_at)
    return 1 if _has_leaks(results) else 0


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    try:
        exit_code = _run()
    except IsolationProofError as exc:
        print(f"isolation_proof: {exc}", file=sys.stderr)
        sys.exit(1)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
