"""Outbound email (Story 1.6: account email verification).

Cross-cutting infra, alongside `shared/llm_client/` and
`shared/llm_client/` -- feature modules (e.g. `auth/service.py`) call
`send_email` here rather than talking to SMTP directly, matching AD-2's
"no raw infra access outside `shared/`" precedent for Weaviate/Neo4j.

stdlib `smtplib` only -- no new dependency for a single outbound call.
Every setting is read lazily from `os.environ` at call time (the same
pattern `auth/service.py`'s `_jwt_secret`/`_access_token_expire_minutes`
use), not added to `main.REQUIRED_ENV_VARS`: the app must still boot with
no mail configured (local dev, CI, a fresh clone with an empty `.env`).
"""

import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)

_DEFAULT_SMTP_PORT = 587
# Real SMTP calls must not hang a threadpool worker indefinitely -- this
# runs inside a Starlette BackgroundTask on Render's free tier, where a
# stuck outbound connection has no caller left to time it out for.
_SMTP_TIMEOUT_SECONDS = 10


def _smtp_port() -> int:
    raw = os.environ.get("SMTP_PORT")
    if not raw:
        return _DEFAULT_SMTP_PORT
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_SMTP_PORT


def _smtp_starttls() -> bool:
    raw = os.environ.get("SMTP_STARTTLS", "true").strip().lower()
    return raw not in ("false", "0", "no")


def send_email(*, to: str, subject: str, body: str) -> None:
    """Sends a plain-text email, or -- if `SMTP_HOST` is unset/blank --
    logs it to the console instead.

    The console fallback is what lets local dev and the whole test suite
    (see `tests/conftest.py`'s autouse `_stub_outbound_email`, which
    monkeypatches this out anyway, but any test that didn't would still
    hit this branch, not a real socket) work with zero mail configuration:
    a verification link just appears in the uvicorn log instead of an
    inbox.

    Raises on real SMTP failure -- this function never swallows an error
    itself; callers that run in a background task (see
    `auth/service.py::send_verification_email`) are the ones responsible
    for deciding a failed send shouldn't surface as a 500 to the request
    that already succeeded.
    """
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        # `warning`, not `info` -- nothing in this project configures a
        # root/handler log level (no `logging.basicConfig`/`dictConfig`
        # anywhere in `app/`), so Python's default root level (WARNING)
        # would silently swallow an `info` record with zero indication
        # anything was logged at all (see `shared/llm_client`'s
        # `_select_passages_within_budget` for the same reasoning already
        # established in this codebase). `warning` is the actual floor for
        # "will be seen without separately wiring up logging config" --
        # and this console fallback existing at all is pointless if the
        # one thing it prints never reaches the terminal.
        logger.warning("SMTP_HOST not configured -- logging email instead of sending.\nTo: %s\nSubject: %s\n\n%s", to, subject, body)
        return

    from_addr = os.environ.get("SMTP_FROM", "").strip() or os.environ.get("SMTP_USERNAME", "").strip()
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()

    if not from_addr:
        # A blank `From` header isn't a bug this function should mail out
        # and let the relay reject silently -- most relays refuse it
        # outright, and the only symptom would otherwise be a caller's
        # generic "failed to send" log line with no indication *why*.
        # Raising here gives that same caller (see
        # `auth/service.py::send_verification_email`'s try/except) a
        # specific, actionable message instead.
        raise ValueError(
            "SMTP_HOST is set but neither SMTP_FROM nor SMTP_USERNAME is -- "
            "at least one is required to set the message's From address."
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to
    message.set_content(body)

    with smtplib.SMTP(host, _smtp_port(), timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
        if _smtp_starttls():
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.send_message(message)
