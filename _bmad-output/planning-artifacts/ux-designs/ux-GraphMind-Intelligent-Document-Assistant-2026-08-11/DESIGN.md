---
name: GraphMind
description: Knowledge-graph + RAG document Q&A assistant — professional-yet-approachable "contemporary tech" tone, executed bold and high-contrast, with citations as the visible trust mechanic.
colors:
  bg: '#FFFFFF'
  surface: '#EDF1FA'
  border: '#C7D2E6'
  text: '#10131A'
  text2: '#454E60'
  primary: '#3861A8'
  accent: '#5B8DEF'
  sky: '#D1EEFE'
  success: '#0A9E5C'
  warning: '#E08600'
  danger: '#E01E1E'
  citation: '#D1EEFE'
  citation-text: '#3064C6'
  robot-a: '#5B8DEF'
  robot-b: '#D1EEFE'
  bg-dark: '#1E222B'
  surface-dark: '#262B35'
  surface2-dark: '#2E333F'
  border-dark: '#3A4150'
  text-dark: '#E4E7EC'
  text2-dark: '#9AA4B5'
  primary-dark: '#5B8CFF'
  accent-dark: '#4C7DFF'
  success-dark: '#3FBD82'
  warning-dark: '#E3A94A'
  danger-dark: '#E4685F'
  citation-dark: '#2A3557'
  citation-text-dark: '#8FB0FF'
typography:
  body:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: 13.5px
    fontWeight: '400'
    lineHeight: '1.55'
  label:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: 12px
    fontWeight: '600'
    letterSpacing: 0.02em
  eyebrow:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: 11px
    fontWeight: '700'
    letterSpacing: 0.04em
  page-title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: 21px
    fontWeight: '700'
  section-title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: 22px
    fontWeight: '700'
  auth-title:
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    fontSize: 20px
    fontWeight: '700'
rounded:
  sm: 6px
  md: 8px
  lg: 12px
  xl: 14px
  full: 9999px
  DEFAULT: 8px
spacing:
  '1': 4px
  '2': 8px
  '3': 12px
  '4': 16px
  '5': 20px
  '6': 24px
  '8': 32px
  '10': 40px
  gutter: 20px
  page-padding: 32px 40px
  section-padding: 48px 5vw
components:
  button-primary:
    background: '{colors.primary}'
    foreground: '#FFFFFF'
    radius: '{rounded.md}'
    padding: '10px 20px'
    fontWeight: '600'
  button-secondary:
    background: '{colors.bg}'
    foreground: '{colors.primary}'
    border: '1px solid {colors.border}'
    radius: '{rounded.md}'
  button-danger:
    background: '{colors.bg}'
    foreground: '{colors.danger}'
    border: '1px solid {colors.border}'
    radius: '{rounded.md}'
  card:
    background: '{colors.bg}'
    border: '1px solid {colors.border}'
    radius: '{rounded.lg}'
  sidebar:
    background: '{colors.primary}'
    background-dark: '{colors.surface-dark}'
    foreground: '#DCE6F5'
    foreground-dark: '{colors.text2-dark}'
    active-background: 'rgba(255,255,255,.14)'
    active-background-dark: 'rgba(91,140,255,.18)'
    radius: '{rounded.md}'
  citation-chip:
    background: '{colors.citation}'
    background-dark: '{colors.citation-dark}'
    foreground: '{colors.citation-text}'
    foreground-dark: '{colors.citation-text-dark}'
    radius: '{rounded.sm}'
    fontWeight: '700'
    fontSize: 11.5px
  status-pill:
    radius: '{rounded.full}'
    fontSize: 11px
    fontWeight: '700'
  robot-mascot:
    antenna-color: '{colors.robot-a}'
    head-gradient: 'linear-gradient(160deg, {colors.robot-a}, {colors.robot-b})'
    body-gradient: 'linear-gradient(160deg, {colors.robot-b}, {colors.robot-a})'
    overlap: '5px'
    position: 'left-aligned above chat input'
    note: 'robot-a/robot-b are locked, independent of the rest of the palette'
  chat-bubble-user:
    background: '{colors.primary}'
    foreground: '#FFFFFF'
    radius: '12px 12px 2px 12px'
  chat-bubble-bot:
    background: '{colors.surface}'
    background-dark: '{colors.surface2-dark}'
    border: '1px solid {colors.border}'
    foreground: '{colors.text}'
    radius: '12px 12px 12px 2px'
---

## Brand & Style

**Reference mocks:** [key-screens-light.html](mockups/key-screens-light.html) · [key-screens-dark.html](mockups/key-screens-dark.html) · [color-theme-options.html](mockups/color-theme-options.html) (exploration record). Mocks illustrate; this spine is the contract and wins on conflict.

GraphMind is a knowledge-graph-plus-RAG document Q&A assistant: you ask a question in plain language, it answers with citations pointing back into your own documents, and it explicitly says "I don't know" when the evidence isn't there. The entire product bet is trust — a user should never have to open the source document themselves to believe an answer — so the interface has to *look* like something that earns that trust: precise, confident, unafraid of contrast, never vague or decorative.

The visual direction is Sirma's own site palette (deep blue brand, white-dominant ground, vibrant blue CTAs, dark charcoal text, clean sans-serif, subtle rounded corners, generous whitespace) pushed into a bolder, more saturated execution — high-contrast blocks of primary color on the sidebar and buttons, crisp borders, no gradients except the two small brand accents (logomark, robot mascot). This reads as "contemporary tech," not "enterprise beige." Structurally it borrows NotebookLM's sources-to-chat relationship: a documents panel that scopes a chat session, with citations that are clickable, first-class, and impossible to miss.

The light theme's original Bold High-Contrast blue read too saturated in practice and was intentionally softened to a baby-blue primary/accent — confident without shouting. The first dark theme (near-black background) was rejected by the user as eye-straining; the shipped dark theme is a deliberately dimmed-charcoal "Soft Dark" variant, tuned for comfortable long-session reading rather than maximum contrast.

## Colors

**Light mode**

- **Primary `{colors.primary}` (#3861A8)** — the brand blue, softened baby-blue rather than the original saturated Bold High-Contrast blue. Darkened from an earlier `#4A7FE0` as a verified WCAG AA contrast fix (applied in parallel across the mock files). Used for the sidebar background, primary buttons, active nav state, page-title accents, and the user's own chat bubbles. This is the color of "GraphMind is doing something" and of user-authored content.
- **Accent `{colors.accent}` (#5B8DEF)** — a touch brighter than primary. Used for links, the dropzone's call-to-action text, "Select all" affordances, and gradients paired with primary (logomark, robot mascot). Never used for full-surface fills the way primary is.
- **Background `{colors.bg}` (#FFFFFF)** and **Surface `{colors.surface}` (#EDF1FA)** — white is the page ground; the pale blue-gray surface tone marks one level of recess (table headers, cards-within-cards, dropzones, meta-item tiles). Two-step depth, no more.
- **Border `{colors.border}` (#C7D2E6)** — the only hairline color. Every card, input, table, and modal edge uses this one value; consistency here is what makes the bold primary fills read as intentional rather than noisy.
- **Text `{colors.text}` (#10131A)** primary / **Text2 `{colors.text2}` (#454E60)** secondary — near-black for headings and body copy, a cooled charcoal-gray for labels, metadata, and captions.
- **Success `{colors.success}` (#0A9E5C)**, **Warning `{colors.warning}` (#E08600)**, **Danger `{colors.danger}` (#E01E1E)** — reserved strictly for ingestion status and destructive actions (Ready/Uploaded pills, delete confirmation, trash-icon hover). Never used decoratively.
- **Citation `{colors.citation}` (#D1EEFE) / citation text (#3064C6)** — `{colors.citation}` is literally `var(--sky)`: the sky-blue token's *sole* sanctioned use is as this citation-chip background (it is not the sidebar background, not the primary, and not used as a general tint anywhere else — that was a rejected experiment, see Do's and Don'ts). Citations are GraphMind's core differentiator made visible, so the chip that carries a citation reference gets its own color identity rather than reusing a generic badge style — it must be instantly recognizable as "this is a proof point," everywhere it appears (chat answers `.cite`, file-type icon tiles in upload rows, doc detail). Darkened from an earlier `#4A7FE0` (UX-DR21): that original pair cleared only 3.22:1 against a 4.5:1 requirement — the chip text is 11.5px/700, which doesn't qualify for WCAG's large-text exception, so 2026-08-11's "accepted deviation" call was based on an exception that didn't actually apply. Closed in Story 3.1 (2026-08-13) by darkening to `#3064C6`, clearing 4.62:1; the mock's other files were never updated to match and should be treated as stale on this one token.

**Dark mode ("Soft Dark")**

- **Background `{colors.bg-dark}` (#1E222B)** — a dimmed charcoal, explicitly *not* near-black. An earlier near-black dark variant was rejected by the user as eye-straining for long sessions; this bg sits in a mid-low luminance band instead.
- **Surface `{colors.surface-dark}` (#262B35)** one step up from bg (cards, panels, the sidebar, table heads); **Surface2 `{colors.surface2-dark}` (#2E333F)** one step further (inputs, nested chips, inner rows). Three-level depth ladder: bg → surface → surface2.
- **Border `{colors.border-dark}` (#3A4150)** — hairlines and dividers throughout.
- **Text `{colors.text-dark}` (#E4E7EC)** — soft off-white, deliberately not pure `#FFF`, to reduce glare (~12.9:1 contrast on bg). **Text2 `{colors.text2-dark}` (#9AA4B5)** muted blue-gray for secondary copy (~5.6:1, passes AA).
- **Primary `{colors.primary-dark}` (#5B8CFF)** / **Accent `{colors.accent-dark}` (#4C7DFF)** — softened, less neon than a literal dark-mode inversion of the light primary would be (~5.0:1 on bg — legible, not harsh).
- **Success `{colors.success-dark}` (#3FBD82)**, **Warning `{colors.warning-dark}` (#E3A94A)**, **Danger `{colors.danger-dark}` (#E4685F)** — same semantic roles as light mode, re-tuned for the darker ground.
- **Citation `{colors.citation-dark}` (#2A3557) / citation text (#8FB0FF)** — the trust-chip identity carried into dark mode with its own re-tuned pair, not just an opacity trick on the light values.

Avoid: introducing a third brand hue beyond primary/accent; using citation color for anything that isn't an actual source reference; using success/warning/danger outside ingestion status and destructive confirmations.

**Contrast exceptions (documented, intentional):** two places use a color that is *not* a raw token value, specifically to clear AA contrast on a colored background:
- The sidebar's inactive nav-link text in light mode is `#E4ECFA` (was `#C9D8EE`) — lighter than the raw value previously used, for AA contrast against the `{colors.primary}` sidebar fill.
- Status-pill text is `#0C7A47` for the `ready`/success state and `#8A5200` for the `uploaded`/warning state — both darker than the raw `{colors.success}` (#0A9E5C) / `{colors.warning}` (#E08600) tokens, specifically tuned for AA contrast against their respective pill background tints. Do not substitute the raw `success`/`warning` token values as pill text color.
- Light-mode citation text is `#3064C6`, not the `#4A7FE0` this doc originally shipped with — see the Citation entry above (UX-DR21) for why.

## Typography

System sans-serif stack throughout (`-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif`) — no custom webfont is specified anywhere in the working files or memlog, so none is assumed here. This is a deliberate "get out of the way, let the color and structure carry the brand" choice consistent with the bold-but-clean direction.

- **`{typography.section-title}`** (22px/700) — top-level section headers on the marketing/overview scroll.
- **`{typography.page-title}`** (21px/700, colored `{colors.primary}`) — the `<h1>` at the top of each authenticated page (Documents, Chat, Graph Preview, Settings).
- **`{typography.auth-title}`** (20px/700, colored `{colors.primary}`) — Login/Register card headings.
- **`{typography.label}`** (12px/600) — form field labels, settings card headers use a close relative at 15px/600.
- **`{typography.eyebrow}`** (11px/700, uppercase, letter-spaced) — table column headers, metadata keys (`.meta-item .k`), status-pill text.
- **`{typography.body}`** (13.5px/400, 1.55 line-height) — chat messages, table cells, general copy. This is the workhorse size across the product.

Rule: only page/section titles and auth headings take `{colors.primary}` as a text color — using primary-as-text anywhere else (body copy, table cells) would dilute it as a heading signal.

## Layout & Spacing

Spacing is a small, consistent scale (`{spacing.1}`–`{spacing.10}`, 4px base unit) plus two named paddings: `{spacing.page-padding}` (32px 40px, the authenticated shell's `.main` content area) and `{spacing.section-padding}` (48px 5vw, full-bleed marketing/overview sections).

- **Authenticated shell**: fixed 220px left sidebar (`{components.sidebar}`) + fluid content area. Sidebar never collapses to icons-only in the current designs — it's a fixed-width text+icon rail.
- **Documents**: full-width table inside the content area, toolbar row (search + filters) directly above it.
- **Chat**: two-column grid, chat window flexible (`1fr`) + fixed 260px right-hand documents-scope panel (`{spacing.gutter}` = 20px gap between them).
- **Modals**: centered, max-width 520px, overlaid on a dimmed diagonal-hatched backdrop (not a flat scrim) — gives upload/delete-confirmation modals a distinct "this is a focused task" feel versus the flat page behind them.
- **Detail panels** (document detail, settings cards): centered, max-width 640px–900px depending on content density (single-column detail vs. two-column settings grid).

Generous whitespace is a stated brand trait — cards get 22–26px internal padding, page heads get 22px bottom margin before content starts. Nothing in the working files specifies responsive/mobile breakpoints; this product is scoped web-only per the memlog, and no mobile layout has been designed.

## Elevation & Depth

Elevation is minimal and functional, not decorative:

- **Resting cards/panels**: no shadow, only a `{colors.border}` hairline — depth comes from the bg→surface color step, not shadow.
- **Sticky nav**: `0 2px 6px rgba(0,0,0,.15)` (light) / `.35` (dark) — just enough to separate it from scrolled content underneath.
- **Modals**: the one place with a real elevation cue — `0 12px 40px rgba(10,20,40,.25)` light / `rgba(0,0,0,.45)` dark — signaling "this floats above everything else and demands attention."
- **Graph nodes**: a soft `0 2px 6px rgba(10,46,99,.25)`-style shadow to read as physical, tappable circles floating on the canvas.

Tonal layering (bg → surface → surface2 in dark mode; bg → surface in light mode) does most of the depth work; shadow is reserved for transient/overlay elements (nav-on-scroll, modals, graph nodes), never for static content cards.

## Shapes

Subtle, consistent rounding drives the "approachable" half of "professional-yet-approachable":

- **`{rounded.sm}` (6px)** — small chips, citation chips, icon buttons, table-adjacent controls.
- **`{rounded.md}` (8px)** — the default: buttons, inputs, toolbar controls, sidebar nav items.
- **`{rounded.lg}` (12px)** — cards, chat window, chat bubbles' three sharp-cornered sides.
- **`{rounded.xl}` (14px)** — auth cards, modals, detail panels — the "important container" radius, one step softer than an ordinary card.
- **`{rounded.full}`** — pills and fully-round elements: status badges, chat text input, toggle switches, the send button.

Chat bubbles use an asymmetric radius (`12px 12px 2px 12px` for the user, mirrored for the bot) — one corner pinched to a near-point, pointing toward the edge the bubble aligns to, giving each message a directional "speech" read without adding a literal tail shape.

## Components

- **Sidebar nav** — Fixed 220px rail. **Light mode:** solid `{colors.primary}` background, white/light-blue (`#DCE6F5`) link text, active item at `rgba(255,255,255,.14)` background with full-white text. **Dark mode:** background switches to `{colors.surface-dark}` (not primary) — a deliberate light/dark asymmetry, keeping the dark shell from turning into a jarring saturated-blue block — with `{colors.text2-dark}` link text and active items picked out at `rgba(91,140,255,.18)` (a primary-tinted wash) with full `{colors.text-dark}` text. Logo mark is a small rounded-square-plus-ring glyph at the top; "Exit" is pinned to the bottom via `margin-top:auto`.
- **Robot mascot** (`{components.robot-mascot}`) — A small recurring brand character built entirely from CSS shapes, positioned left-aligned directly above the chat input row with exactly 5px of overlap onto the input field's top edge, as if stepping onto it. Anatomy: a thin antenna with a dot tip (`{colors.robot-a}`), a rounded head (gradient `{colors.robot-a}`→`{colors.robot-b}`) with two white eye-dots and a small ear/fin nub, and a rounded body (gradient `{colors.robot-b}`→`{colors.robot-a}`) with two angled arm details flaring off each side. **`{colors.robot-a}` (#5B8DEF) and `{colors.robot-b}` (#D1EEFE) are their own locked, independent tokens** — set once early in the design process and deliberately never touched by any of the several full-palette revisions that followed (baby-pink experiment, baby-blue softening, the sky-blue-dominant redesign, the D1EEFE-as-primary experiment). It is coincidental, not derivative, that `{colors.robot-a}`/`{colors.robot-b}` now numerically match `{colors.accent}`/`{colors.sky}` in the final locked palette — treat the robot tokens as their own namespace so a future palette change doesn't accidentally repaint the mascot. This went through several iterations (inline-left, full-body-shifted-right) before landing here — the final position is a small, subtle, Claude-Code-CLI-indicator-style presence rather than a large illustrated character. Because it recurs on every Chat visit, treat it as a brand element on par with the logomark, not a one-off decoration.
- **Citation chip** (`{components.citation-chip}`) — Small pill/chip, `{colors.citation}` background with `{colors.citation-text}` text, bold, 11.5px, `{rounded.sm}` corners. Appears inline inside bot chat messages (`.cite`) and as the file-type icon tile in upload rows. This is the single most important visual token in the product — it's what makes a claim verifiable at a glance — and must never be restyled to look like an ordinary badge or tag.
- **Chat bubbles** (`{components.chat-bubble-user}` / `-bot`) — User messages: `{colors.primary}` fill, white text (dark-mode: dark text `#1E222B` on the lighter primary-dark fill, for contrast), right-aligned. Bot messages: `{colors.surface}`/`{colors.surface2-dark}` fill with a border, left-aligned, containing inline citation chips.
- **Status pill** (`{components.status-pill}`) — Fully-rounded, bold 11px uppercase-weight text. `ready` uses a success tint background with success text; `uploaded` uses a warning tint. Extend the same pattern for `extracting`/`graphing`/`failed` states named in the PRD's ingestion pipeline (FR-4), reusing warning for in-progress states and danger for `failed`.
- **Buttons** — Primary: solid `{colors.primary}` fill, white text, `{rounded.md}`, no border. Secondary: white/surface2 fill, primary-colored text, bordered. Danger: same shape as secondary, danger-colored text — danger is a text-color signal, not a filled-red button, until a confirmation step.
- **Modal** — `{rounded.xl}` container on a diagonal-hatched dimmed backdrop, header/body/footer three-part structure, footer right-aligns its actions.
- **Dropzone** — Dashed border, `{colors.surface}`/`{surface2-dark}` fill, centered text with an accent-colored call-to-action phrase.
- **Toggle switch** — 40×22px pill track, `{colors.border}` off / `{colors.primary}` on, white thumb — used on Settings for theme and account toggles.
- **Document table row** — `<table class="doclist">` rows. Header cells (`th`): 11px uppercase, letter-spaced `0.04em`, `{colors.text2}`, `{colors.surface}` background, `12px 16px` padding, `1px solid {colors.border}` bottom hairline. Body cells (`td`): `13.5px`/`{typography.body}`, `13px 16px` padding, same `1px solid {colors.border}` bottom hairline (last row's hairline suppressed). Columns: Title, Type, Status, Uploaded, trash-icon (unlabeled). Row itself carries no distinct background/hover token in the mock beyond the shared cell hairlines.
- **Document search bar / toolbar** — `.toolbar`: flex row, `10px` gap, wraps, `16px` bottom margin, vertically centered items. Select/search inputs: `8px 10px` padding, `1px solid {colors.border}`, `{rounded.md}` (8px) corners, `13px` text, `{colors.bg}` (#fff) fill, `{colors.text}` text.
- **Chat composer row** — `.chat-input-bar`: `1px solid {colors.border}` top border, `14px 20px` padding, column flex with `10px` gap. Inner `.input-row`: flex row, `8px` gap. Text input: flex-1, `10px 14px` padding, `1px solid {colors.border}`, `{rounded.full}` (20px) corners, `13.5px` text. Send button: `{colors.primary}` fill, white text, no border, `10px 18px` padding, `{rounded.full}` (20px) corners, `13px`/600 weight text.
- **Graph canvas** — `.graph-canvas`: `480px` height, `{colors.bg}` (#fff) fill, `1px solid {colors.border}`, `{rounded.xl}` (14px) corners, `overflow:hidden`. Nodes (`.gnode`): absolutely positioned circles (`border-radius:50%`), sized per entity prominence (~52–78px diameter in the mock), filled from `{colors.primary}`/`{colors.accent}`/`{colors.success}` (varied per node, not semantic-status-bound here), white centered label text (10.5px/700), `0 2px 6px rgba(10,46,99,.25)` shadow per the Elevation spec's "graph nodes" rule.
- **Settings card** — `.settings-grid`: two-column grid, `20px` gap, `900px` max-width. Each card follows the base `{components.card}` spec (`{colors.bg}` fill, `1px solid {colors.border}`, `{rounded.lg}` 12px corners); the Delete Account card additionally uses a `{colors.danger}`-tinted border/background per the danger-zone pattern.
- **Document detail panel** — `.detail-panel`: `640px` max-width, centered, `{colors.bg}` (#fff) fill, `1px solid {colors.border}`, `{rounded.xl}` (14px) corners, `26px` padding. Heading (`h3`): `18px`/700, `{colors.primary}` text, tight bottom margin. Metadata grid (`.meta-grid`): two-column grid, `14px` gap, `18px` vertical margin, each cell an eyebrow-style key (`{typography.eyebrow}`) over a value.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Give every citation its own `{colors.citation}` chip, everywhere a claim is sourced | Let a citation blend into ordinary badge/tag styling |
| Keep the sidebar solid-primary in light mode, surface-toned (not primary) in dark mode | Reuse the light-mode sidebar treatment verbatim in dark mode |
| Use the Soft Dark palette's dimmed-charcoal `{colors.bg-dark}` (#1E222B) | Ship a near-black dark background — already tried and rejected as eye-straining |
| Keep the robot mascot small, left-aligned, 5px-overlapping the chat input top edge | Enlarge it into a full illustrated character or shift it to the right |
| Reserve success/warning/danger strictly for ingestion status and destructive actions | Use status colors decoratively elsewhere in the UI |
| Use `{colors.accent}` for links, CTAs-within-text, and gradients | Fill large chrome surfaces (sidebar, nav) with accent instead of primary |
| Keep corner radii inside the documented scale (6/8/12/14/full) | Introduce a new radius value ad hoc per component |
| Use `{colors.sky}` (#D1EEFE) only as the citation-chip background (`{colors.citation}`) | Use sky as the sidebar background, as primary, or as a general-purpose light tint elsewhere — tried three times, rejected each time |
| Treat `{colors.robot-a}`/`{colors.robot-b}` as their own locked tokens for the mascot only | Wire the mascot's gradient to `{colors.accent}`/`{colors.sky}` directly, which would make it drift if those change |
