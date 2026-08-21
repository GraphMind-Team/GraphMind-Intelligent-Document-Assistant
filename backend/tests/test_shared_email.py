"""Direct unit tests for `app.shared.email.send_email` (Story 1.6).

Every other test in the suite exercises this module only indirectly, via
`auth.service.send_verification_email` -- and `tests/conftest.py`'s
autouse `_stub_outbound_email` monkeypatches `service.send_email` out
entirely, so none of those tests ever actually run this file's code.
These tests call `send_email` itself, with `smtplib.SMTP` mocked out, so
the console fallback, port/STARTTLS parsing, and message construction
are covered directly rather than only by inference.
"""

from unittest.mock import MagicMock

import pytest

from app.shared import email as email_module


@pytest.fixture(autouse=True)
def _clear_smtp_env(monkeypatch):
    """Every test in this file controls its own SMTP_* env explicitly --
    without this, whatever a developer happens to have in their real
    `.env` (loaded by `shared/data_access/session.py`'s `load_dotenv()`
    at import time) would leak into these tests' "unconfigured" cases."""
    for key in (
        # BREVO_API_KEY belongs in this list as much as any SMTP_* var:
        # it is now checked FIRST by send_email, so a real key in a
        # developer's .env would silently route every "unconfigured" and
        # every SMTP test in this file down the HTTP branch instead.
        "BREVO_API_KEY",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_STARTTLS",
    ):
        monkeypatch.delenv(key, raising=False)


def test_send_email_with_no_smtp_host_logs_instead_of_sending(monkeypatch, caplog):
    fake_smtp_class = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)

    with caplog.at_level("WARNING"):
        email_module.send_email(to="maria@example.com", subject="Verify", body="link: http://x/verify")

    fake_smtp_class.assert_not_called()
    assert "maria@example.com" in caplog.text
    assert "link: http://x/verify" in caplog.text


def test_send_email_sends_via_smtp_when_host_configured(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USERNAME", "apikey")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "noreply@graphmind.example")

    fake_smtp = MagicMock()
    fake_smtp_class = MagicMock()
    fake_smtp_class.return_value.__enter__.return_value = fake_smtp
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)

    email_module.send_email(to="maria@example.com", subject="Verify", body="link: http://x/verify")

    fake_smtp_class.assert_called_once_with("smtp.example.com", 2525, timeout=email_module._SMTP_TIMEOUT_SECONDS)
    fake_smtp.starttls.assert_called_once()
    fake_smtp.login.assert_called_once_with("apikey", "secret")
    fake_smtp.send_message.assert_called_once()
    sent_message = fake_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "noreply@graphmind.example"
    assert sent_message["To"] == "maria@example.com"
    assert sent_message["Subject"] == "Verify"


def test_send_email_skips_starttls_and_login_when_not_configured(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "noreply@graphmind.example")
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    # No SMTP_USERNAME/SMTP_PASSWORD -- send_email must not call login()
    # with empty credentials.

    fake_smtp = MagicMock()
    fake_smtp_class = MagicMock()
    fake_smtp_class.return_value.__enter__.return_value = fake_smtp
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)

    email_module.send_email(to="maria@example.com", subject="Verify", body="body")

    fake_smtp.starttls.assert_not_called()
    fake_smtp.login.assert_not_called()
    fake_smtp.send_message.assert_called_once()


def test_send_email_falls_back_to_username_as_from_address(monkeypatch):
    """SMTP_FROM is optional -- SMTP_USERNAME doubles as the From address
    when SMTP_FROM isn't set, matching send_email's own fallback."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "apikey@graphmind.example")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")

    fake_smtp = MagicMock()
    fake_smtp_class = MagicMock()
    fake_smtp_class.return_value.__enter__.return_value = fake_smtp
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)

    email_module.send_email(to="maria@example.com", subject="Verify", body="body")

    sent_message = fake_smtp.send_message.call_args.args[0]
    assert sent_message["From"] == "apikey@graphmind.example"


def test_send_email_raises_a_clear_error_with_no_from_address_available(monkeypatch):
    """SMTP_HOST configured but neither SMTP_FROM nor SMTP_USERNAME set --
    rather than mailing out a blank From header for the relay to reject
    silently, send_email must fail loudly with an actionable message."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")

    fake_smtp_class = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)

    with pytest.raises(ValueError, match="SMTP_FROM"):
        email_module.send_email(to="maria@example.com", subject="Verify", body="body")

    fake_smtp_class.assert_not_called()


def test_smtp_port_falls_back_to_default_on_garbage_value(monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "not-a-number")
    assert email_module._smtp_port() == email_module._DEFAULT_SMTP_PORT


def test_smtp_starttls_defaults_to_true(monkeypatch):
    assert email_module._smtp_starttls() is True
    monkeypatch.setenv("SMTP_STARTTLS", "false")
    assert email_module._smtp_starttls() is False
    monkeypatch.setenv("SMTP_STARTTLS", "0")
    assert email_module._smtp_starttls() is False


# ---------------------------------------------------------------------------
# Brevo HTTP transport (added when Render's free tier turned out to block
# every SMTP port -- 25, 465 and 587 -- making smtplib undeliverable there
# regardless of configuration).
# ---------------------------------------------------------------------------


def test_brevo_api_key_takes_precedence_over_a_configured_smtp_host(monkeypatch):
    """The precedence direction is the whole point, not an arbitrary pick.

    A deployment mid-migration has BOTH set: the old SMTP values are still
    filled in, and the API key is newly added. Preferring SMTP there would
    mean the variable someone just set to fix delivery gets ignored in
    favour of the one that cannot deliver -- failing exactly where the fix
    was supposed to apply.
    """
    fake_smtp_class = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)
    fake_post = MagicMock(return_value=MagicMock(status_code=201))
    monkeypatch.setattr(email_module.httpx, "post", fake_post)

    monkeypatch.setenv("BREVO_API_KEY", "key-123")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")

    email_module.send_email(to="user@example.com", subject="Hi", body="Body")

    fake_post.assert_called_once()
    fake_smtp_class.assert_not_called()


def test_brevo_send_posts_the_expected_payload(monkeypatch):
    fake_post = MagicMock(return_value=MagicMock(status_code=201))
    monkeypatch.setattr(email_module.httpx, "post", fake_post)
    monkeypatch.setenv("BREVO_API_KEY", "key-123")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")

    email_module.send_email(to="user@example.com", subject="Verify", body="Link")

    kwargs = fake_post.call_args.kwargs
    assert kwargs["headers"]["api-key"] == "key-123"
    payload = kwargs["json"]
    assert payload["sender"] == {"email": "sender@example.com"}
    assert payload["to"] == [{"email": "user@example.com"}]
    assert payload["subject"] == "Verify"
    assert payload["textContent"] == "Link"


def test_brevo_falls_back_to_smtp_username_for_the_sender(monkeypatch):
    fake_post = MagicMock(return_value=MagicMock(status_code=201))
    monkeypatch.setattr(email_module.httpx, "post", fake_post)
    monkeypatch.setenv("BREVO_API_KEY", "key-123")
    monkeypatch.setenv("SMTP_USERNAME", "fallback@example.com")

    email_module.send_email(to="user@example.com", subject="Hi", body="Body")

    assert fake_post.call_args.kwargs["json"]["sender"] == {"email": "fallback@example.com"}


def test_brevo_without_any_sender_address_raises_a_named_error(monkeypatch):
    fake_post = MagicMock(return_value=MagicMock(status_code=201))
    monkeypatch.setattr(email_module.httpx, "post", fake_post)
    monkeypatch.setenv("BREVO_API_KEY", "key-123")

    with pytest.raises(ValueError, match="SMTP_FROM"):
        email_module.send_email(to="user@example.com", subject="Hi", body="Body")

    fake_post.assert_not_called()


def test_brevo_error_response_raises_with_the_body_included(monkeypatch):
    """An unverified sender address is the likeliest failure on a fresh
    Brevo account, and it is indistinguishable from any other 400 unless
    the response body survives into the message the caller logs."""
    fake_post = MagicMock(
        return_value=MagicMock(status_code=400, text='{"message":"Sender not valid"}')
    )
    monkeypatch.setattr(email_module.httpx, "post", fake_post)
    monkeypatch.setenv("BREVO_API_KEY", "key-123")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")

    with pytest.raises(RuntimeError, match="Sender not valid"):
        email_module.send_email(to="user@example.com", subject="Hi", body="Body")


def test_no_transport_configured_still_logs_instead_of_sending(monkeypatch, caplog):
    """The console fallback must survive the new branch -- local dev and
    CI configure neither transport."""
    fake_post = MagicMock()
    monkeypatch.setattr(email_module.httpx, "post", fake_post)
    fake_smtp_class = MagicMock()
    monkeypatch.setattr(email_module.smtplib, "SMTP", fake_smtp_class)

    with caplog.at_level("WARNING"):
        email_module.send_email(to="user@example.com", subject="Hi", body="Body")

    fake_post.assert_not_called()
    fake_smtp_class.assert_not_called()
    assert "user@example.com" in caplog.text
