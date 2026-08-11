# GraphMind — Accessibility Review (WCAG 2.2 AA lens)

Reviewed: `DESIGN.md`, `EXPERIENCE.md`, `mockups/key-screens-light.html`, `mockups/key-screens-dark.html`.

## Verdict

**Fails WCAG 2.2 AA as specified.** The text/background pairs (body text, secondary text, borders) are strong, but three of the product's most-used and most-symbolic components — the primary button/CTA fill, the sidebar nav link text, and the citation chip (the entire product's trust mechanic) — fall short of the 4.5:1 normal-text minimum in light mode. The mockups also contain effectively zero ARIA: no `role="dialog"`, no `aria-live`, no `aria-label` on the disabled checkboxes EXPERIENCE.md itself mandates labeling, no accessible distinction for status pills beyond color+text. EXPERIENCE.md's Accessibility Floor is a reasonable set of intentions but is unenforced by both the tokens and the mocks that are supposed to demonstrate them.

---

## 1. Color contrast — computed ratios

Method: WCAG relative-luminance contrast formula, computed directly from the hex values in `DESIGN.md`'s `colors` block. Large-text exemption (3:1) applies only to ≥24px regular or ≥18.66px **and** font-weight ≥700 (bold); the mock's own CSS sets buttons/labels at 600 weight, which does not qualify as "bold" for this purpose, so it is *not* applied unless noted.

### Light mode

| Pair | Ratio | AA (normal 4.5:1 / large 3:1 / UI 3:1) | Verdict |
|---|---|---|---|
| `text` #10131A on `bg` #FFFFFF | 18.58:1 | 4.5:1 | Pass (AAA) |
| `text2` #454E60 on `bg` #FFFFFF | 8.36:1 | 4.5:1 | Pass |
| `text` on `surface` #EDF1FA | 16.43:1 | 4.5:1 | Pass |
| `text2` on `surface` | 7.39:1 | 4.5:1 | Pass |
| **white `#fff` on `primary` #4A7FE0** (button-primary text, `.btn-primary` @ 14px/600) | **3.89:1** | 4.5:1 | **FAIL** |
| `primary` #4A7FE0 text on `bg` #FFFFFF (button-secondary text, links, `.btn-secondary` @ 14px/400) | 3.89:1 | 4.5:1 | **FAIL** |
| `danger` #E01E1E on `bg` #FFFFFF (button-danger text) | 4.80:1 | 4.5:1 | Pass (narrow) |
| **sidebar link text `#DCE6F5` on `primary` #4A7FE0 (sidebar bg, light mode)** | **3.09:1** | 4.5:1 | **FAIL** |
| **citation-text `#4A7FE0` on citation-chip bg `#D1EEFE`** (11.5px/700 — still under the 18.66px bold large-text threshold) | **3.22:1** | 4.5:1 | **FAIL** |
| `success` #0A9E5C on white (status-pill text, worst case if rendered at full saturation) | 3.47:1 | 4.5:1 | **FAIL** (see note below) |
| `warning` #E08600 on white | 2.77:1 | 4.5:1 | **FAIL** |
| `primary` #4A7FE0 as page-title text (21px/700 — qualifies as large text) on white | 3.89:1 | 3:1 (large) | Pass |
| `border` #C7D2E6 on `bg` (non-text UI-component contrast, e.g. input/card outlines) | 1.52:1 | 3:1 | **FAIL** (informational only — see note) |

**Note on status pills / success-warning-danger as text:** `DESIGN.md` never specifies the actual pill background tint (only "success tint background with success text" / "warning tint"), so the exact fg/bg pair used for `Ready`/`Uploaded` badges cannot be verified precisely — the table above tests the semantic color used as text directly on white/surface as the worst-case reading. If pills instead use a pale tint background *and* the full-saturation success/warning/danger hue as the foreground text, verify against the actual chosen tint, not just white — but as specified, `warning` #E08600 fails even against pure white, so any real (necessarily less contrasty) tint will fail worse. **This needs an explicit pill-background token before build**, and the token needs to be re-picked to clear 4.5:1 with its paired text color.

**Note on `border` #C7D2E6:** 1.52:1 is expected — border hairlines aren't required to hit 3:1 unless they're the *sole* means of conveying a required non-text UI boundary (e.g., an input's focus-adjacent resting state, distinguishing an unfocused input/button edge from the page). Flagging only because `DESIGN.md` states border is "the only hairline color... every card, input, table, and modal edge uses this one value" — if any of those edges is relied on as the only cue for an interactive element's boundary (vs. an adjacent focus ring), it falls under WCAG 1.4.11 Non-text Contrast (3:1) and currently fails. Recommend explicitly confirming inputs/buttons don't depend on the border alone (they don't appear to, given filled/bordered button variants), and keep the focus ring as the actual boundary-and-state indicator.

### Dark mode ("Soft Dark")

| Pair | Ratio | AA | Verdict |
|---|---|---|---|
| `text-dark` #E4E7EC on `bg-dark` #1E222B | 12.84:1 | 4.5:1 | Pass |
| `text2-dark` #9AA4B5 on `bg-dark` | 6.33:1 | 4.5:1 | Pass |
| `primary-dark` #5B8CFF on `bg-dark` (links/text use) | 5.03:1 | 4.5:1 | Pass |
| `accent-dark` #4C7DFF on `bg-dark` | 4.31:1 | 4.5:1 | **FAIL** (marginal — DESIGN.md's own claimed "~5.0:1" doesn't match accent-dark specifically; it matches primary-dark) |
| dark text `#1E222B` on `primary-dark` #5B8CFF (user chat bubble, dark mode) | 5.03:1 | 4.5:1 | Pass |
| `text2-dark` on `surface-dark` #262B35 (sidebar link text, dark mode) | 5.65:1 | 4.5:1 | Pass |
| `text-dark` on `surface-dark` (sidebar active-item text, dark mode) | 11.45:1 | 4.5:1 | Pass |
| citation-text-dark `#8FB0FF` on citation-dark bg `#2A3557` | 5.63:1 | 4.5:1 | Pass |
| `danger-dark` #E4685F on `bg-dark` | 4.89:1 | 4.5:1 | Pass (narrow) |
| `success-dark` #3FBD82 on `bg-dark` | 6.68:1 | 4.5:1 | Pass |
| `warning-dark` #E3A94A on `bg-dark` | 7.61:1 | 4.5:1 | Pass |
| `border-dark` #3A4150 on `bg-dark` | 1.56:1 | 3:1 (UI) | Same caveat as light-mode border |

**Dark mode passes essentially everywhere tested**, including the citation chip — the one component that fails hardest in light mode is fine in dark. This is a meaningful light/dark asymmetry: dark mode's re-tuned citation pair (`#8FB0FF`/`#2A3557`, 5.63:1) is genuinely accessible; light mode's citation pair (`#4A7FE0`/`#D1EEFE`, 3.22:1) is not, despite DESIGN.md calling the citation chip "the single most important visual token in the product."

### Summary of contrast failures (light mode, in priority order)

1. **Citation-chip text on citation-chip background — 3.22:1, needs 4.5:1.** This is the highest-priority fix: the citation chip is explicitly the product's core trust/differentiation device (DESIGN.md: "the single most important visual token in the product"), rendered at a small 11.5px bold size that does not qualify for the large-text exemption. As specified, sighted low-vision users are the ones least able to read the exact thing meant to build trust. Fix: darken `citation-text` (e.g. toward a deeper blue) or darken the `citation` chip background — dark mode's re-tuned pair proves a compliant version of this concept is achievable.
2. **Sidebar nav link text on primary background — 3.09:1, needs 4.5:1.** Every authenticated page's primary navigation fails contrast in light mode. Fix: darken `primary` slightly for the sidebar-specific fill, or lighten the `#DCE6F5` link color, or use full-white nav text (only the *active* item currently gets full white).
3. **Primary button and secondary-button text — 3.89:1, needs 4.5:1.** Affects every primary CTA and every secondary/bordered button app-wide (Upload, Ask/Send if styled as `.btn-primary`, Save, Cancel, etc.), plus inline links using `accent`/`primary` as text color at body size. Fix: darken `primary` overall, or introduce a separate "text-safe" darker variant of primary for on-white / white-on-primary text use distinct from the fill-only decorative uses.
4. **Warning/success used as pill or badge text at full saturation fails outright (2.77:1 / 3.47:1)**, and the actual pill background tint is unspecified in the source docs, so this cannot be fully verified — flag as a build-blocking gap: pick and document explicit tint+text pairs for all five status-pill states (Uploaded/Extracting/Graphing/Ready/Failed) and re-check contrast once chosen.
5. Dark-mode `accent-dark` on `bg-dark` (4.31:1) marginally misses 4.5:1 if ever used for small body-size text/links directly on `bg-dark`; low priority since DESIGN.md scopes accent's *dark* text-role usage narrowly, but worth a token check before it's used for a link.

---

## 2. Keyboard / focus handling (EXPERIENCE.md — Accessibility Floor & Interaction Primitives)

**What's stated (good, but underspecified):**
- "Focus rings must remain visible against both light and dark theme backgrounds — themeable, not hardcoded to one palette." Correct principle, but no actual focus-ring color/style token exists anywhere in `DESIGN.md`'s `colors`/`components` — there is no `focus-ring` or `outline` token at all. Nothing to implement against. **Gap: no focus-indicator token specified**, and neither mockup file defines a `:focus` or `:focus-visible` style (confirmed by inspection — no `outline`, `:focus`, or `box-shadow`-on-focus rule appears in either `key-screens-light.html` or `key-screens-dark.html`).
- "Tab order... follows visual reading order" is asserted but not demonstrated; the mocks are static HTML with no explicit `tabindex` management, which is fine as a default (DOM order = visual order in the current layout) but becomes fragile the moment the two-column Chat layout (chat window `1fr` + 260px scope panel) is implemented with CSS Grid/Flexbox reordering, since visual order and DOM order can silently diverge. Recommend an explicit note that no CSS `order`/`flex-direction: row-reverse` is used on any layout that carries interactive content.
- Delete-confirm and destructive actions: EXPERIENCE.md correctly calls out that Cancel/Confirm Delete "cannot depend on hover or pointer-only affordances," but the inline confirm box's focus management on open is unspecified — when the confirm box appears inline (not a modal), does focus move to it, or to the Confirm/Cancel buttons? Screen-reader users get no cue that new interactive content appeared unless focus moves or the region is announced (see ARIA section below).
- Composer submission (Enter or click Ask) is fine and standard; no primitive gap there.
- **Unaddressed: Escape key handling for the inline delete-confirm box.** EXPERIENCE.md specifies Escape/Cancel closes the *modal* (Upload) but the delete-confirm pattern is explicitly inline, not modal, and Escape behavior for it is never mentioned — should Escape collapse it back to the resting Delete button? Currently undefined.
- **Unaddressed: focus return.** When a modal or inline confirm closes (Cancel, Confirm, or Escape), where does focus go? Not specified anywhere in EXPERIENCE.md. Standard practice (WCAG 2.4.3, 2.4.7) is to return focus to the triggering control (Upload button, trash icon) — this should be stated explicitly as a requirement, not left to implementation.
- **Unaddressed: graph canvas keyboard access.** Graph Preview is read-only with "no click-to-query, no drag-to-rearrange" — good, that avoids a whole class of keyboard-trap risk — but if nodes are individually inspectable/hoverable for details (common in node-link diagrams), there's no mention of keyboard equivalents (e.g., tabbing through nodes, arrow-key navigation) or whether node detail-on-hover has a keyboard/focus equivalent at all. If nodes carry no interaction, this is moot, but the spine doesn't say either way.

## 3. Semantic / ARIA considerations for custom components

Direct inspection of both mockup files found **exactly one accessibility attribute in the entire codebase**: `aria-hidden="true"` on the robot mascot's container (`key-screens-light.html` line 346, mirrored in dark). No `role`, `aria-label`, `aria-live`, `aria-modal`, `aria-describedby`, or native `<dialog>`/`<button>` semantics appear anywhere else that was sampled (buttons, checkboxes, modal, status pills). This is consistent with the mocks being purely visual references (as `DESIGN.md`/`EXPERIENCE.md` both state the mocks "illustrate; spine/DESIGN wins on conflict"), but since EXPERIENCE.md's Accessibility Floor makes specific ARIA-shaped promises, it's worth recording exactly what's missing relative to those promises:

- **Robot mascot** — correctly `aria-hidden="true"` and EXPERIENCE.md explicitly calls it "decorative and non-interactive." This one is actually done right; no further work needed beyond preserving `aria-hidden` in the real implementation.
- **Status pills** — EXPERIENCE.md requires status "not rely on color alone — always paired with the text label," which the mocks do visually (badge text + tint). But the *text itself* (e.g., "READY", "FAILED") needs no extra ARIA if it's real DOM text (a `<span>PROCESSING</span>` styled as a pill needs nothing special) — the risk is only if a future implementation renders the label as a background-image, icon-font glyph, or `::before` content, which would strip it from the accessibility tree. Recommend an explicit note: "status-pill text must be real, selectable DOM text, not a pseudo-element or icon-font glyph."
- **Disabled checkboxes (Chat scope panel, non-Ready docs)** — EXPERIENCE.md explicitly requires: "must expose their disabled reason (e.g. via `aria-label` incorporating the status) rather than only showing '(processing)' as visual-only text." The mockup directly contradicts this requirement: line 365 of `key-screens-light.html` is `<div class="doc-chip" style="opacity:.5;"><input type="checkbox" disabled><span>NDA_Draft_Rev2.pdf (processing)</span></div>` — the checkbox has no `aria-label`, `aria-describedby`, or `title`; the "(processing)" text lives in a sibling `<span>`, not associated with the checkbox via `for`/`id`, `aria-labelledby`, or `aria-describedby`. A screen reader landing on the checkbox alone announces only "checkbox, dimmed/unavailable, unchecked" with no status. **This is a concrete, checkable spec violation between EXPERIENCE.md and its own reference mock** and should be fixed at implementation (e.g., wrap in `<label>`, or add `aria-label="NDA_Draft_Rev2.pdf, processing, not yet selectable"`).
- **Chat message bubbles** — no `role` distinguishing user vs. assistant turns, and (more importantly) no `aria-live` region on the chat thread at all. Without `aria-live="polite"` (or a comparable pattern) on the message list/container, a screen-reader user gets no announcement when a new assistant answer streams in — they'd have to manually re-navigate to discover it. This is unaddressed in both EXPERIENCE.md and the mocks and should be added as a requirement: the chat thread container needs a live region (polite, not assertive, to avoid interrupting mid-typing) and each turn should carry enough semantic structure (e.g., `role="log"` on the thread, or clear heading/labeling per turn) to be navigable.
- **Citation chip** — EXPERIENCE.md states citations "must be programmatically distinguishable from surrounding answer text (not just visually) so screen-reader users can identify where a claim's evidence is cited." Good intent, but no concrete mechanism is specified (e.g., wrapping in `<cite>`, or `<span role="doc-noteref" aria-label="Citation: Ch. 4, Vendor_Agreement_2026.pdf">`). Since the chip is explicitly non-interactive/non-clickable in v1 (no jump-to-source), the simplest compliant approach is a semantic inline element (`<cite>` or a labelled `<span>`) rather than a generic styled `<span class="cite">` as the mock currently uses (`.cite` class, no semantic tag) — currently the mock's citation markup is visually distinct only, exactly the anti-pattern the spine warns against.
- **Modal (Upload)** — no `role="dialog"`, no `aria-modal="true"`, no `aria-labelledby` pointing at the modal-head `<h3>`, and no evidence of an initial-focus or focus-trap implementation in the static mock (expected, since it's a static reference, but EXPERIENCE.md doesn't call these requirements out explicitly either — it only says "background is not interactive while modal is open" and "Escape/Cancel closes"). Focus trap (Tab cycling stays within the modal) and initial focus placement (typically the first focusable element or the dropzone) should be added as explicit requirements, not left implicit.
- **Inline delete-confirm box** — not a modal, so it needs its own semantic treatment: minimally an `aria-live="polite"` announcement or ideally a `role="alertdialog"`-equivalent pattern if it's to interrupt attention appropriately, plus programmatic association between the confirm text (the deletion-boundary explanation) and the Confirm/Cancel buttons so screen-reader users get the plain-language warning before acting, not just "button: Confirm Delete" with the context floating elsewhere in the DOM.
- **Refusal ("I don't know") bubble** — EXPERIENCE.md is explicit and correct that this "must be announced distinctly from a normal answer to assistive tech, not merely styled differently for sighted users," but this is listed as an **open design gap with no mock** — so there is currently no answer for *how* (a `role` change? a leading `aria-label` "Refusal:"? a different live-region announcement pattern?). Flagging as inherited from the open-gaps list, not new, but worth restating here since it's squarely an accessibility question and shouldn't be resolved as a visual-only decision when it eventually gets designed.

## 4. Additional gaps not otherwise captured

- **No token for focus-ring color/width/style** in `DESIGN.md`, in either light or dark palette, despite EXPERIENCE.md mandating visible, themeable focus rings. This should be added to the color/component spec before build (e.g., a `focus-ring` token distinct from `border`, likely `accent`-based with sufficient 3:1 non-text contrast against both `bg` and `surface`/`surface-dark`).
- **Graph canvas color-only encoding risk**: DESIGN.md doesn't state whether entity/relationship *types* on the Graph Preview canvas are distinguished by color alone (a common node-link diagram pattern) — if so, that's a 1.4.1 Use-of-Color violation in the making (node color alone conveying entity type). No mention of shape, label, or icon differentiation. Worth flagging before the graph visual spec is finalized.
- **Diagonal-hatched modal backdrop**: purely decorative per DESIGN.md's description, should carry no semantic weight and needs no ARIA — no issue, just confirming no gap here.
- **Reduced motion**: nothing in either doc addresses `prefers-reduced-motion` for any transitions/animations (progress bars, modal open/close, theme toggle). Not a blocking AA criterion by default but worth a one-line note given how much of the product involves live progress states (upload, ingestion pipeline).
- **Text resize / zoom**: fixed 220px sidebar and fixed 260px Chat scope panel are stated as non-collapsing, non-responsive ("no mobile layout... breakpoints... specified"). At 200% browser zoom (WCAG 1.4.4) a fixed two-fixed-column + fluid-center layout on a typical laptop viewport risks horizontal scrolling or content clipping. Not evaluated in mockups (desktop-only reference). Recommend a zoom/reflow check once implemented, since nothing in the spine currently guards against it.

---

## Files reviewed

- `_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/DESIGN.md`
- `_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/EXPERIENCE.md`
- `_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/mockups/key-screens-light.html`
- `_bmad-output/planning-artifacts/ux-designs/ux-GraphMind-Intelligent-Document-Assistant-2026-08-11/mockups/key-screens-dark.html`
