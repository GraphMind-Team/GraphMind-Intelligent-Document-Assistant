"""`app.main._validate_env` coverage.

That function is the project's one fail-fast gate on deployment
misconfiguration -- it runs at import time, before the app can serve
anything -- and until now it had no tests of its own (the `_validate_env`
covered in `test_eval_harness.py` is a different function, belonging to
`scripts/eval_harness.py`).

The `JWT_SECRET` length floor is the reason this file exists: PyJWT signs
and verifies quite happily with an 8-byte HS256 key, emitting only an
`InsecureKeyLengthWarning` that nothing in a deployed process is watching,
so a weak secret is otherwise accepted in silence and every token in the
system inherits its strength.
"""

import pytest

from app.main import _MIN_JWT_SECRET_BYTES, _validate_env


def _set_valid_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg2://test:test@localhost:5432/test")
    monkeypatch.setenv("JWT_SECRET", "a" * _MIN_JWT_SECRET_BYTES)


def test_passes_when_everything_is_set(monkeypatch):
    _set_valid_env(monkeypatch)
    _validate_env()  # does not raise


@pytest.mark.parametrize("missing", ["DATABASE_URL", "JWT_SECRET"])
def test_names_the_missing_variable(monkeypatch, missing):
    _set_valid_env(monkeypatch)
    monkeypatch.delenv(missing)

    with pytest.raises(RuntimeError) as excinfo:
        _validate_env()
    assert missing in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_present_but_blank_secret_is_treated_as_missing(monkeypatch, blank):
    """`.strip()`, not mere presence -- an env var set to whitespace is a
    real deployment shape (a dashboard field cleared by hand), and it must
    fail as "missing" rather than sail past into the length check and be
    reported as a confusing "0 bytes"."""
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", blank)

    with pytest.raises(RuntimeError) as excinfo:
        _validate_env()
    assert "Missing required environment variable" in str(excinfo.value)


def test_rejects_a_secret_below_the_hs256_minimum(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "a" * (_MIN_JWT_SECRET_BYTES - 1))

    with pytest.raises(RuntimeError) as excinfo:
        _validate_env()
    message = str(excinfo.value)
    assert "JWT_SECRET is too short" in message
    assert str(_MIN_JWT_SECRET_BYTES) in message


def test_accepts_a_secret_exactly_at_the_minimum(monkeypatch):
    """The boundary is inclusive -- RFC 7518 requires a key *at least* as
    long as the hash output, so exactly 32 bytes is valid, not one short."""
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "a" * _MIN_JWT_SECRET_BYTES)

    _validate_env()  # does not raise


def test_length_is_measured_in_bytes_not_characters(monkeypatch):
    """A non-ASCII secret encodes to more bytes than it has characters,
    and the byte string is what actually keys the HMAC -- so a 31-character
    Cyrillic secret is comfortably over the floor and must be accepted."""
    _set_valid_env(monkeypatch)
    secret = "я" * (_MIN_JWT_SECRET_BYTES - 1)
    assert len(secret) < _MIN_JWT_SECRET_BYTES
    assert len(secret.encode("utf-8")) >= _MIN_JWT_SECRET_BYTES
    monkeypatch.setenv("JWT_SECRET", secret)

    _validate_env()  # does not raise


def test_the_error_never_echoes_the_secret_itself(monkeypatch):
    """A startup traceback is one of the easier things to end up in a
    shared log, so the rejection may report the length and nothing else."""
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("JWT_SECRET", "hunter2-far-too-short")

    with pytest.raises(RuntimeError) as excinfo:
        _validate_env()
    assert "hunter2" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Optional token-lifetime vars. Absent is fine (the code has defaults); a
# value that cannot be honoured is not. Both feed a JWT `exp`, so zero or
# negative issues a token already expired when created -- login answers 200
# and /auth/me immediately 401s, an endless sign-in loop with nothing in the
# logs naming the cause. `int()` accepts "0" and "-30", so the ValueError
# guard the getters already had never caught them.
# ---------------------------------------------------------------------------

LIFETIME_VARS = ["ACCESS_TOKEN_EXPIRE_MINUTES", "EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS"]


@pytest.mark.parametrize("name", LIFETIME_VARS)
def test_an_absent_lifetime_var_is_fine(monkeypatch, name):
    _set_valid_env(monkeypatch)
    monkeypatch.delenv(name, raising=False)

    _validate_env()  # does not raise -- the code default applies


@pytest.mark.parametrize("name", LIFETIME_VARS)
@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_lifetime_var_is_fine(monkeypatch, name, blank):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv(name, blank)

    _validate_env()  # treated as absent, not as zero


@pytest.mark.parametrize("name", LIFETIME_VARS)
@pytest.mark.parametrize("bad", ["0", "-1", "-30"])
def test_a_non_positive_lifetime_refuses_to_boot(monkeypatch, name, bad):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv(name, bad)

    with pytest.raises(RuntimeError) as excinfo:
        _validate_env()
    assert name in str(excinfo.value)
    assert "positive" in str(excinfo.value)


@pytest.mark.parametrize("name", LIFETIME_VARS)
def test_an_unparseable_lifetime_refuses_to_boot(monkeypatch, name):
    """Rejected rather than silently defaulted: `1440m` quietly yielding 60
    is a lifetime twenty-four times shorter than configured, with no signal
    that anything was ignored."""
    _set_valid_env(monkeypatch)
    monkeypatch.setenv(name, "1440m")

    with pytest.raises(RuntimeError) as excinfo:
        _validate_env()
    assert name in str(excinfo.value)


@pytest.mark.parametrize("name", LIFETIME_VARS)
def test_a_positive_lifetime_boots(monkeypatch, name):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv(name, "120")

    _validate_env()  # does not raise
