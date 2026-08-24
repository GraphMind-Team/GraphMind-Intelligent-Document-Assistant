"""Tests for the HTML verification email (`shared/email/templates.py`).

The plain-text body has been covered indirectly since Story 1.6; these
cover the HTML alternative added when the email was redesigned, and in
particular the two failure modes that are invisible from the backend and
only show up in someone's inbox:

  * an `<img>` pointing at an SVG, which Gmail and Outlook refuse to render
    (this is what made the first version show a broken-image icon), and
  * a copy key present in `templates.py` but missing from a language's
    catalog, which would raise inside `send_verification_email`'s
    `except Exception` and silently send nothing at all.
"""

import re

import pytest

from app.auth import service
from app.shared.email.templates import REQUIRED_COPY_KEYS, verification_email_html
from app.shared.i18n.catalogs import SUPPORTED_LANGUAGES, _MESSAGES

VERIFY_URL = "https://app.example.com/verify-email?token=abc.def.ghi"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_every_language_defines_every_copy_key_the_template_reads(language):
    """`t()` falls back to English for a missing key and only raises if it is
    missing there too -- so a half-translated email would ship silently, in
    English, rather than failing. Assert each language carries its own entry
    instead of relying on that fallback."""
    missing = [
        key for key in REQUIRED_COPY_KEYS if f"verify_email.{key}" not in _MESSAGES[language]
    ]
    assert missing == [], f"{language} is missing: {missing}"


@pytest.mark.parametrize("language", SUPPORTED_LANGUAGES)
def test_verification_email_renders_in_every_language(language, monkeypatch):
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.example.com")

    html = service._verification_email_html(
        "Maria Ivanova", VERIFY_URL, language, "https://app.example.com"
    )

    # The link has to survive into both the button and the paste-it-yourself
    # fallback -- an email whose only copy of the token is inside an <a> the
    # reader's client mangles is an email they cannot act on.
    assert html.count(VERIFY_URL) >= 2
    assert _MESSAGES[language]["verify_email.button"] in html
    # No unsubstituted placeholder left behind by a missing format argument.
    assert "{full_name}" not in html
    assert "{expire_hours}" not in html


def test_the_mascot_is_a_png_and_not_an_svg():
    """Regression: the first version of this email pointed at
    `/email-robot.svg`. Gmail and Outlook refuse to render an <img> whose
    source is an SVG, so every recipient saw a broken-image icon where the
    hero art should be. PNG is the only raster format all of them render."""
    html = service._verification_email_html(
        "Maria", VERIFY_URL, "en", "https://app.example.com"
    )

    sources = re.findall(r'<img[^>]+src="([^"]+)"', html)
    assert sources, "the email should still carry hero art"
    assert all(src.endswith(".png") for src in sources), sources


def test_hero_keeps_a_solid_background_color_behind_its_gradient():
    """Outlook drops `background-image: linear-gradient(...)` entirely. With
    no `bgcolor` underneath it, the hero's white headline and white button
    would land on a white background -- invisible."""
    html = verification_email_html(
        verify_url=VERIFY_URL,
        robot_src="https://app.example.com/email-robot.png",
        copy={key: f"copy-{key}" for key in REQUIRED_COPY_KEYS},
    )

    hero = html[html.index("Hero"): html.index("Body card")]
    assert "linear-gradient" in hero
    assert 'bgcolor="#0EA5E9"' in hero


def test_container_is_not_a_fixed_width_table():
    """Regression: a `width="600"` attribute beats `max-width:100%` in real
    table layout, so the message kept its 600px on a 390px phone and forced
    sideways scrolling. The responsive container must stay percentage-based,
    with the fixed width confined to the Outlook-only ghost table."""
    html = verification_email_html(
        verify_url=VERIFY_URL,
        robot_src="https://app.example.com/email-robot.png",
        copy={key: f"copy-{key}" for key in REQUIRED_COPY_KEYS},
    )

    # Strip every HTML comment -- that removes both the Outlook ghost table
    # (a conditional comment, and the one place a fixed 600px is correct) and
    # the explanatory comments, which quote markup they don't apply. What's
    # left is the markup every other client actually lays out.
    live_markup = re.sub(r"<!--.*?-->", "", html, flags=re.S)
    assert 'width="600"' in html, "the Outlook ghost table should still be there"
    assert 'width="600"' not in live_markup
    assert "max-width:600px" in live_markup


def test_send_verification_email_sends_both_a_text_and_an_html_part(monkeypatch):
    """The HTML is an *alternative*, never a replacement: a client that
    can't or won't render it still needs the plain-text link."""
    import uuid

    sent = {}
    monkeypatch.setattr(service, "send_email", lambda **kwargs: sent.update(kwargs))
    monkeypatch.setenv("FRONTEND_ORIGIN", "https://app.example.com")

    service.send_verification_email(uuid.uuid4(), "maria@example.com", "Maria", "en")

    assert sent["to"] == "maria@example.com"
    assert "/verify-email?token=" in sent["body"]
    assert sent["html_body"].lstrip().startswith("<!DOCTYPE html")
    assert "/verify-email?token=" in sent["html_body"]
