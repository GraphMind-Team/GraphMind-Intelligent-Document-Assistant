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


def test_every_line_height_leaves_real_headroom_over_its_font_size():
    """Regression: `text-size-adjust: 100%` (the other test below) does not
    stop every client's font-boosting -- reported from a real Gmail Android
    send, some words were still overlapping after that fix landed, most
    visibly the button label wrapping to two lines with the old
    `line-height: 1` (i.e. zero space between them). A ratio comfortably
    above 1 is the fix that holds regardless of whether a client honors the
    reset at all: even a client that boosts font-size while leaving
    line-height untouched needs real slack before two lines start to touch.

    1.4 is the floor actually shipped in `templates.py` as of this test
    (see the ratios printed while fixing this) -- not a generic email best
    practice number, so if a future edit legitimately needs to go tighter,
    lower this constant deliberately rather than fighting the test.
    """
    html = verification_email_html(
        verify_url=VERIFY_URL,
        robot_src="https://app.example.com/email-robot.png",
        copy={key: f"copy-{key}" for key in REQUIRED_COPY_KEYS},
    )

    min_ratio = 1.4
    too_tight = []
    for style in re.findall(r'style="([^"]*)"', html):
        font_size = re.search(r"font-size:\s*(\d+)px", style)
        line_height = re.search(r"line-height:\s*(\d+)px", style)
        if not (font_size and line_height):
            continue
        fs, lh = int(font_size.group(1)), int(line_height.group(1))
        if lh / fs < min_ratio:
            too_tight.append((style, fs, lh, round(lh / fs, 2)))

    assert too_tight == []


def test_button_survives_wrapping_to_two_lines():
    """The concrete failure the ratio test above guards abstractly: on a
    narrow phone the longer BG/DE button labels wrap to two lines (English's
    doesn't). Assert those two lines render with daylight between them,
    not the touching-or-overlapping pair `line-height: 1` produced."""
    html = verification_email_html(
        verify_url=VERIFY_URL,
        robot_src="https://app.example.com/email-robot.png",
        copy={
            **{key: f"copy-{key}" for key in REQUIRED_COPY_KEYS},
            "button": "Потвърди имейл адреса",
        },
    )
    button_style = re.search(
        r'<a href="[^"]*"[^>]*style="([^"]*)">Потвърди', html
    ).group(1)
    font_size = int(re.search(r"font-size:\s*(\d+)px", button_style).group(1))
    line_height = int(re.search(r"line-height:\s*(\d+)px", button_style).group(1))

    assert line_height > font_size, "two wrapped lines would touch or overlap"


def test_head_resets_text_size_adjust_to_none():
    """`none`, not a percentage -- a real Gmail iOS send showed adjacent
    words fused together with no space ("Вашите" + "документи"), and a
    `100%` reset (this test's original assertion) didn't fix it: per MDN,
    a percentage value still leaves the browser's text-autosizing
    algorithm running, only clamping its output ratio, whereas `none`
    disables the algorithm outright. `none` in the `<style>` block AND
    inline on `<body>`, since some mobile webviews honor one but strip
    the other."""
    html = verification_email_html(
        verify_url=VERIFY_URL,
        robot_src="https://app.example.com/email-robot.png",
        copy={key: f"copy-{key}" for key in REQUIRED_COPY_KEYS},
    )

    style_block = re.search(r"<style[^>]*>(.*?)</style>", html, re.S)
    assert style_block and "text-size-adjust: none" in style_block.group(1)
    assert "100%" not in style_block.group(1)

    body_tag = re.search(r"<body[^>]*>", html).group(0)
    assert "text-size-adjust:none" in body_tag


def test_every_text_bearing_element_disables_size_adjust_inline():
    """Regression, same real Gmail iOS send as the test above: the
    `<style>`-block-only reset wasn't enough, because Gmail's app is known
    to strip `<style>` blocks in some paths, and `text-size-adjust`
    inheriting correctly through several layers of nested email tables
    isn't reliable either. Every element that actually carries visible
    text needs its own inline declaration -- inheriting from `<body>`
    isn't good enough. Spacer cells (`&nbsp;`-only, `font-size:0`) are the
    one deliberate exception: nothing there for the algorithm to mismeasure."""
    html = verification_email_html(
        verify_url=VERIFY_URL,
        robot_src="https://app.example.com/email-robot.png",
        copy={key: f"copy-{key}" for key in REQUIRED_COPY_KEYS},
    )

    missing = []
    for match in re.finditer(r'<(?:td|p|h1|a)\b[^>]*style="([^"]*)"', html):
        style = match.group(1)
        if "font-size:0" in style:
            continue  # spacer cell -- no text to mismeasure
        if ("font-size" in style or "font-family" in style) and "text-size-adjust:none" not in style:
            missing.append(style[:60])

    assert missing == []


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
