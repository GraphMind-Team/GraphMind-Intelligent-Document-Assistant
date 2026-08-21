"""Outbound email (Story 1.6: account email verification).

Cross-cutting infra, alongside `shared/llm_client/` and
`shared/llm_client/` -- feature modules (e.g. `auth/service.py`) call
`send_email` here rather than talking to SMTP directly, matching AD-2's
"no raw infra access outside `shared/`" precedent for Weaviate/Neo4j.

Two transports, chosen by which environment variables are set (see
`send_email`): Brevo's HTTP API, or SMTP. The HTTP one exists because
Render's free tier blocks outbound traffic on ports 25, 465 and 587 --
every port SMTP uses -- so `smtplib` cannot deliver anything at all from
the deployed environment, no matter how it is configured. An HTTPS call
on 443 is not blocked.

Every setting is read lazily from `os.environ` at call time (the same
pattern `auth/service.py`'s `_jwt_secret`/`_access_token_expire_minutes`
use), not added to `main.REQUIRED_ENV_VARS`: the app must still boot with
no mail configured (local dev, CI, a fresh clone with an empty `.env`).
"""

import logging
import os
import smtplib
from email.message import EmailMessage

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_SMTP_PORT = 587
# Real SMTP calls must not hang a threadpool worker indefinitely -- this
# runs inside a Starlette BackgroundTask on Render's free tier, where a
# stuck outbound connection has no caller left to time it out for.
_SMTP_TIMEOUT_SECONDS = 10

# Brevo's transactional-send endpoint. Chosen over SMTP for the deployed
# environment for the port-blocking reason in this module's docstring, and
# over Resend/SendGrid specifically because its free tier verifies a
# single *sender address* (a Gmail address, confirmed by clicking a link)
# rather than requiring a whole authenticated domain -- this project does
# not own one. 300 sends/day on the free plan.
_BREVO_URL = "https://api.brevo.com/v3/smtp/email"
# Matches _SMTP_TIMEOUT_SECONDS' reasoning: this runs inside a Starlette
# BackgroundTask with no caller left to time it out.
_HTTP_TIMEOUT_SECONDS = 10


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


def _sender_address() -> str:
    """The From address, shared by both transports.

    `SMTP_FROM` is reused rather than introducing an `EMAIL_FROM`: it
    already holds exactly this value in every configured environment, and
    a second variable meaning the same thing is one more thing to set
    wrong. Falls back to `SMTP_USERNAME` for the SMTP case where the two
    are conventionally the same address.
    """
    return os.environ.get("SMTP_FROM", "").strip() or os.environ.get("SMTP_USERNAME", "").strip()


def _send_via_brevo(*, api_key: str, to: str, subject: str, body: str) -> None:
    """Sends through Brevo's HTTP API.

    Raises on failure, like the SMTP path -- `send_email`'s contract is
    that it never swallows a send error, and the background-task caller
    in `auth/service.py` is what decides that shouldn't 500 a request.
    """
    from_addr = _sender_address()
    if not from_addr:
        # Same reasoning as the SMTP branch's own check: a blank From is
        # rejected by the relay with a message the caller never sees, so
        # fail here with one that names the actual missing variable.
        raise ValueError(
            "BREVO_API_KEY is set but neither SMTP_FROM nor SMTP_USERNAME is -- "
            "one is required for the message's From address."
        )

    response = httpx.post(
        _BREVO_URL,
        headers={"api-key": api_key, "content-type": "application/json"},
        json={
            "sender": {"email": from_addr},
            "to": [{"email": to}],
            "subject": subject,
            "textContent": body,
        },
        timeout=_HTTP_TIMEOUT_SECONDS,
    )
    if response.status_code >= 400:
        # Body included: Brevo reports the actionable cause here (an
        # unverified sender address is the overwhelmingly likely one on a
        # fresh account, and is invisible from the status code alone).
        raise RuntimeError(
            f"Brevo rejected the send ({response.status_code}): {response.text[:300]}"
        )


def send_email(*, to: str, subject: str, body: str) -> None:
    """Sends a plain-text email, or -- if no transport is configured --
    logs it to the console instead.

    Transport is chosen by environment, most-specific first:

      1. `BREVO_API_KEY` set -> Brevo's HTTP API. Required on Render's
         free tier, which blocks every SMTP port outright (see the module
         docstring), so SMTP there fails no matter how it is configured.
      2. `SMTP_HOST` set -> SMTP, unchanged.
      3. neither -> console fallback.

    Checked in that order, not the reverse, so an environment that has
    both (a deployment carrying its old SMTP values forward while gaining
    an API key -- exactly what migrating looks like) uses the transport
    that can actually deliver, rather than the one that will time out.

    The console fallback is what lets local dev and the whole test suite
    (see `tests/conftest.py`'s autouse `_stub_outbound_email`, which
    monkeypatches this out anyway, but any test that didn't would still
    hit this branch, not a real socket) work with zero mail configuration:
    a verification link just appears in the uvicorn log instead of an
    inbox.

    Raises on a real send failure, either transport -- this function
    never swallows an error
    itself; callers that run in a background task (see
    `auth/service.py::send_verification_email`) are the ones responsible
    for deciding a failed send shouldn't surface as a 500 to the request
    that already succeeded.
    """
    brevo_key = os.environ.get("BREVO_API_KEY", "").strip()
    if brevo_key:
        _send_via_brevo(api_key=brevo_key, to=to, subject=subject, body=body)
        return

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

    from_addr = _sender_address()
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
