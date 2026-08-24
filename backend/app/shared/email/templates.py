"""HTML rendering for outbound email (Story 1.6's verification email).

Split out of `auth/service.py` rather than inlined there: this is
presentation, not verification logic, and keeping the two apart means a
future second HTML email (password reset, say) reuses `_shell` instead of
copy-pasting a table layout.

Deliberately old-school HTML-email markup -- nested tables, inline styles,
fixed 600px width, no flexbox/grid, no external stylesheet -- because mail
clients (Outlook's Word rendering engine above all) support none of the
modern CSS a normal web page would use. This is the actual convention for
transactional email, not a stylistic choice.

Two rules the layout below keeps that are easy to break by accident:

  * **Every image is a PNG, and no layout depends on one loading.** SVG is
    refused outright by Gmail and Outlook (the first version of this email
    used one, and it rendered as a broken-image icon), and *any* remote
    image is blocked by default in most clients until the reader clicks
    "show images". So the mascot is a PNG, and the hero it sits in draws
    its own color from `bgcolor` -- with images off, the email still reads
    as a finished, branded page rather than a stack of grey boxes.

  * **Gradients are decoration layered over a solid `bgcolor`.** Outlook
    ignores `background-image: linear-gradient(...)` entirely; clients that
    support it get the brand gradient, and the rest get the flat brand
    color underneath. Never put text on a gradient without a `bgcolor` that
    keeps it legible on its own.

The visual language (gradient hero, soft-tinted icon tiles, 01/02/03 step
numerals, white pill CTA on brand) is lifted from the marketing page in
`frontend/src/pages/LandingPage.jsx` so the email reads as the same product,
and the copy is the landing page's own, translated in
`shared/i18n/catalogs.py`.
"""

import html
from collections.abc import Mapping

# ---------------------------------------------------------------------------
# Palette -- the light-theme tokens from frontend/src/index.css, hardcoded.
# A CSS custom property means nothing outside a browser, and an email has no
# theme to inherit: always the light variant, because a client that ignores
# prefers-color-scheme for mail would otherwise render dark-on-dark.
# ---------------------------------------------------------------------------
_BRAND = "#0EA5E9"           # --accent, the solid fallback under the gradient
_BRAND_GRADIENT = "linear-gradient(135deg, #38BDF8 0%, #0EA5E9 45%, #2563EB 100%)"  # --grad-brand
_PRIMARY = "#0369A1"         # --primary
_INK = "#0B1A2B"             # --text
_INK_SOFT = "#4C6076"        # --text2
_MUTED = "#8296AB"
_BORDER = "#D3E3F2"          # --border
_TILE_BG = "#E0F2FE"         # --sky, the soft tint behind the feature glyphs
_PAGE_BG = "#F7FAFD"         # --bg
_CARD_BG = "#FFFFFF"         # --card-bg

_FONT = (
    "Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"
)
_FONT_DISPLAY = (
    "'Space Grotesk',Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
)

# The three "what you get" rows and the three "how it works" steps, mirroring
# LandingPage.jsx's own FEATURES/STEPS arrays. The glyphs are single unicode
# characters rather than icon images on purpose: an icon that is blocked (see
# the module docstring) leaves a hole, whereas a character always renders.
_FEATURES = (
    ("upload", "↑"),        # upwards arrow
    ("answers", "✓"),       # check mark
    ("connections", "◆"),   # black diamond
)
_STEPS = (("add", "01"), ("ask", "02"), ("follow", "03"))

# Every copy key this template reads, as suffixes under `verify_email.` in
# `shared/i18n/catalogs.py`. Exported so `auth/service.py` builds the mapping
# from this list rather than a hand-kept duplicate that can drift out of sync.
REQUIRED_COPY_KEYS = (
    "preheader",
    "eyebrow",
    "hero_title",
    "hero_body",
    "button",
    "greeting",
    "intro",
    "what_you_get",
    "how_it_works",
    "fallback_intro",
    "expiry",
    "ignore",
    "footer_tagline",
    "footer_copyright",
    *(f"feature_{key}_title" for key, _ in _FEATURES),
    *(f"feature_{key}_body" for key, _ in _FEATURES),
    *(f"step_{key}_title" for key, _ in _STEPS),
    *(f"step_{key}_body" for key, _ in _STEPS),
)


def _e(value: str) -> str:
    return html.escape(value)


def _logo_lockup() -> str:
    """The site header's logo: a gradient squircle with a white ring inside,
    next to the wordmark. Built from a table cell rather than an image so it
    survives images being blocked (Outlook renders it as a flat brand-colored
    square, which is a fine degradation)."""
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center">
<tr>
<td width="36" height="36" bgcolor="{_BRAND}" style="width:36px; height:36px; border-radius:11px; background-color:{_BRAND}; background-image:{_BRAND_GRADIENT}; text-align:center; vertical-align:middle;">
<div style="width:12px; height:12px; margin:0 auto; border:2px solid #FFFFFF; border-radius:50%; font-size:0; line-height:0;">&nbsp;</div>
</td>
<td style="padding-left:10px; font-family:{_FONT_DISPLAY}; font-size:19px; font-weight:700; letter-spacing:-0.01em; color:{_INK};">GraphMind</td>
</tr>
</table>"""


def _button(*, href: str, label: str) -> str:
    """A "bulletproof" button: the color lives on a table cell (which every
    client paints) and the padding on the anchor (so the whole pill is the
    click target), instead of on a styled `<a>` alone that Outlook would
    render as bare underlined text."""
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center">
<tr>
<td align="center" bgcolor="#FFFFFF" style="border-radius:999px; background-color:#FFFFFF;">
<a href="{href}" target="_blank" style="display:inline-block; padding:15px 38px; font-family:{_FONT}; font-size:15px; font-weight:700; line-height:1; color:{_PRIMARY}; text-decoration:none; border-radius:999px;">{_e(label)}</a>
</td>
</tr>
</table>"""


def _section_title(text: str) -> str:
    return (
        f'<p style="margin:0 0 20px; font-family:{_FONT_DISPLAY}; font-size:19px; '
        f'font-weight:700; letter-spacing:-0.01em; color:{_INK};">{_e(text)}</p>'
    )


def _feature_row(*, glyph: str, title: str, body: str, is_last: bool) -> str:
    """One "what you get" row: a soft-tinted round tile with a glyph, then the
    title and body beside it. A two-cell table, not a float or flexbox --
    neither exists in Outlook."""
    spacer = "" if is_last else '<tr><td colspan="2" height="18" style="height:18px; font-size:0; line-height:0;">&nbsp;</td></tr>'
    return f"""<tr><td colspan="2" style="padding:0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td width="44" valign="top" style="width:44px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0">
<tr><td width="44" height="44" align="center" valign="middle" bgcolor="{_TILE_BG}" style="width:44px; height:44px; border-radius:12px; background-color:{_TILE_BG}; font-family:{_FONT}; font-size:19px; line-height:44px; color:{_PRIMARY};">{glyph}</td></tr>
</table>
</td>
<td valign="top" style="padding-left:14px;">
<p style="margin:0 0 4px; font-family:{_FONT_DISPLAY}; font-size:15px; font-weight:700; color:{_INK};">{_e(title)}</p>
<p style="margin:0; font-family:{_FONT}; font-size:14px; line-height:22px; color:{_INK_SOFT};">{_e(body)}</p>
</td>
</tr>
</table>
</td></tr>{spacer}"""


def _step_row(*, numeral: str, title: str, body: str, is_last: bool) -> str:
    """One "how it works" step. Same two-cell shape as a feature row, but the
    tile is the step numeral in brand color on the page tint -- matching the
    landing page's own 01/02/03 treatment."""
    spacer = "" if is_last else '<tr><td colspan="2" height="16" style="height:16px; font-size:0; line-height:0;">&nbsp;</td></tr>'
    return f"""<tr><td colspan="2" style="padding:0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
<tr>
<td width="44" valign="top" style="width:44px; font-family:{_FONT_DISPLAY}; font-size:20px; font-weight:700; line-height:22px; color:{_BRAND};">{numeral}</td>
<td valign="top" style="padding-left:14px;">
<p style="margin:0 0 4px; font-family:{_FONT_DISPLAY}; font-size:15px; font-weight:700; color:{_INK};">{_e(title)}</p>
<p style="margin:0; font-family:{_FONT}; font-size:14px; line-height:22px; color:{_INK_SOFT};">{_e(body)}</p>
</td>
</tr>
</table>
</td></tr>{spacer}"""


def _divider(space_above: int = 28, space_below: int = 28) -> str:
    return f"""<tr><td colspan="2" style="padding:{space_above}px 0 {space_below}px;">
<div style="height:1px; background-color:{_BORDER}; font-size:0; line-height:0;">&nbsp;</div>
</td></tr>"""


def verification_email_html(
    *, verify_url: str, robot_src: str, copy: Mapping[str, str]
) -> str:
    """Renders the verification email's HTML alternative.

    `copy` is every string already translated -- see `REQUIRED_COPY_KEYS` for
    the keys and `auth/service.py::_verification_email_html` for where they
    come from. This module lays text out; `shared/i18n/catalogs.py` owns what
    the text says.
    """
    url = _e(verify_url)
    c = copy

    features = "".join(
        _feature_row(
            glyph=glyph,
            title=c[f"feature_{key}_title"],
            body=c[f"feature_{key}_body"],
            is_last=index == len(_FEATURES) - 1,
        )
        for index, (key, glyph) in enumerate(_FEATURES)
    )
    steps = "".join(
        _step_row(
            numeral=numeral,
            title=c[f"step_{key}_title"],
            body=c[f"step_{key}_body"],
            is_last=index == len(_STEPS) - 1,
        )
        for index, (key, numeral) in enumerate(_STEPS)
    )

    return f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="x-apple-disable-message-reformatting" />
<title></title>
</head>
<body style="margin:0; padding:0; width:100%; background-color:{_PAGE_BG};">

<!-- Preheader: hidden in the email itself, but it is what most inbox list
     views print next to the subject. Without one, clients quote whatever
     markup comes first instead. -->
<div style="display:none; max-height:0; overflow:hidden; opacity:0; mso-hide:all;">{_e(c["preheader"])}</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{_PAGE_BG};">
<tr>
<td align="center" style="padding:32px 12px 40px;">

<!-- The container is `width="100%"` capped by `max-width`, NOT a fixed
     `width="600"`: a table's width *attribute* beats `max-width` in real
     layout, so a fixed one keeps its 600px on a 390px phone and forces the
     whole message to scroll sideways. Outlook ignores `max-width` and would
     otherwise run full-bleed, so it gets a fixed 600px ghost table of its
     own through the mso conditional -- the standard way to have both. -->
<!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%; max-width:600px; margin:0 auto;">

<!-- ============ Header ============ -->
<tr>
<td align="center" style="padding:8px 0 24px;">{_logo_lockup()}</td>
</tr>

<!-- ============ Hero ============ -->
<!-- bgcolor carries the brand color on its own; the gradient is layered on
     top for the clients that support it (see the module docstring). -->
<tr>
<td align="center" bgcolor="{_BRAND}" style="border-radius:20px; background-color:{_BRAND}; background-image:{_BRAND_GRADIENT}; padding:40px 32px 44px;">

<img src="{_e(robot_src)}" width="150" height="150" alt="" style="display:block; width:150px; height:150px; border:0; outline:none; margin:0 auto 22px;" />

<p style="margin:0 0 12px; font-family:{_FONT}; font-size:11px; font-weight:700; letter-spacing:0.12em; text-transform:uppercase; color:#D8F1FF;">{_e(c["eyebrow"])}</p>

<h1 style="margin:0 0 14px; font-family:{_FONT_DISPLAY}; font-size:32px; line-height:38px; font-weight:700; letter-spacing:-0.02em; color:#FFFFFF;">{_e(c["hero_title"])}</h1>

<p style="margin:0 0 28px; font-family:{_FONT}; font-size:15px; line-height:24px; color:#E4F5FF;">{_e(c["hero_body"])}</p>

{_button(href=url, label=c["button"])}

</td>
</tr>

<!-- ============ Body card ============ -->
<tr>
<td style="padding:0;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{_CARD_BG}" style="margin-top:16px; background-color:{_CARD_BG}; border:1px solid {_BORDER}; border-radius:20px;">
<tr>
<td style="padding:36px 34px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">

<tr><td colspan="2">
<p style="margin:0 0 12px; font-family:{_FONT_DISPLAY}; font-size:17px; font-weight:700; color:{_INK};">{_e(c["greeting"])}</p>
<p style="margin:0; font-family:{_FONT}; font-size:15px; line-height:24px; color:{_INK_SOFT};">{_e(c["intro"])}</p>
</td></tr>

{_divider()}

<tr><td colspan="2">{_section_title(c["what_you_get"])}</td></tr>
{features}

{_divider()}

<tr><td colspan="2">{_section_title(c["how_it_works"])}</td></tr>
{steps}

{_divider(space_above=30, space_below=22)}

<!-- Fine print: the raw link for readers whose client mangles the button,
     then expiry and the "ignore this" line. -->
<tr><td colspan="2">
<p style="margin:0 0 8px; font-family:{_FONT}; font-size:13px; line-height:20px; color:{_MUTED};">{_e(c["fallback_intro"])}</p>
<p style="margin:0 0 16px; font-family:{_FONT}; font-size:13px; line-height:20px; word-break:break-all;"><a href="{url}" target="_blank" style="color:{_PRIMARY}; text-decoration:underline;">{url}</a></p>
<p style="margin:0; font-family:{_FONT}; font-size:13px; line-height:20px; color:{_MUTED};">{_e(c["expiry"])} {_e(c["ignore"])}</p>
</td></tr>

</table>
</td>
</tr>
</table>
</td>
</tr>

<!-- ============ Footer ============ -->
<tr>
<td align="center" style="padding:28px 20px 0;">
<p style="margin:0 0 6px; font-family:{_FONT_DISPLAY}; font-size:14px; font-weight:700; color:{_INK_SOFT};">{_e(c["footer_tagline"])}</p>
<p style="margin:0; font-family:{_FONT}; font-size:12px; line-height:18px; color:{_MUTED};">{_e(c["footer_copyright"])}</p>
</td>
</tr>

</table>
<!--[if mso]></td></tr></table><![endif]-->

</td>
</tr>
</table>
</body>
</html>"""
