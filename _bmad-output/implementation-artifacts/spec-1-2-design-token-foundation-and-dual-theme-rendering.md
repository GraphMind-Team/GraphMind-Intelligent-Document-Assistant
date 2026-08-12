---
title: 'Story 1.2: Design-token foundation and dual-theme rendering'
type: 'feature'
created: '2026-08-12'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: 'f47dd8d3301193eb261b90e48ff0c08e2100094d'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** DESIGN.md's palette, typography, spacing, and radius scale exist only as planning-doc values. Nothing in the frontend consumes them yet, and two token gaps (status-pill pairs for 3 of 5 states, the focus-ring token) block any component work needing to render correctly in both themes.

**Approach:** Turn DESIGN.md's values into Tailwind v4 CSS-custom-property tokens (colors swap per theme via `:root` vs `[data-theme="dark"]`; typography/spacing/radius are theme-invariant), add a `ThemeContext` that defaults to light (ignores system `prefers-color-scheme` for the initial value), persists an explicit override to `localStorage`, and flips `data-theme` on `<html>` at runtime, and close the open token gaps. Frontend-only — zero file overlap with the parallel auth work on 1.3/1.4.

## Boundaries & Constraints

**Always:**
- Every DESIGN.md value (colors, typography, spacing, radius) becomes a named CSS custom property consumed via Tailwind v4's `@theme` block — no component hardcodes a raw hex, px, or em value going forward.
- Colors defined twice: raw values in `:root` (light, always the default) and re-defined under `:root[data-theme="dark"]` for the explicit override. No `prefers-color-scheme` query — dark only activates via explicit toggle.
- Citation chip pair stays exactly `#4A7FE0` text on `#D1EEFE` background — a documented, accepted AA deviation (UX-DR21). Do not re-tune.
- Status-pill pairs, all clearing 4.5:1: `ready` `#E1F1EA`/`#0C7A47`, `uploaded` `#FBEFD6`/`#8A5200` (from the mocks, unchanged). `extracting`/`graphing` reuse `uploaded`'s pair (DESIGN.md: "reusing warning for in-progress states"). `failed` is new: light `#FBE2E2`/`#CA1B1B` (4.64:1); dark `rgba(228,104,95,.06)` over `bg-dark` with `#E4685F` text (4.55:1) — lower opacity than `ready`/`uploaded`'s dark tint (`.16`) because `danger-dark` at `.16` only clears 3.96:1, below AA.
- Focus-ring token: `primary` (`#3861A8`) in light mode, `accent-dark` (`#4C7DFF`) in dark mode — both verified ≥3:1 against `bg` and `surface`/`surface-dark`, distinct from `border`, reusing existing tokens rather than inventing a new hue. Apply via `:focus-visible` on every interactive element (buttons, links, inputs) in both themes.
- Sidebar inactive-link text: use `#DCE6F5` (the structured `components.sidebar.foreground` value, not the prose-only `#E4ECFA` mention — both clear 4.5:1 against the current `primary`, so use the structured one).
- `ThemeContext` (`frontend/src/context/ThemeContext.jsx`) defaults to `light`, reads/writes an explicit `localStorage` override, and sets `data-theme` on `document.documentElement`. Every token-consuming surface must reflect a theme change immediately, no reload.
- Wrap all CSS transitions/animations in `@media (prefers-reduced-motion: no-preference)` so `prefers-reduced-motion: reduce` suppresses them (UX-DR28).
- Retrofit `HealthPage.jsx`'s hardcoded Tailwind slate/red classes to the new tokens, as the first concrete proof the system works, and add a small temporary theme-toggle affordance there so the runtime switch (AC5) is visually verifiable before Epic 5 ships the real Settings toggle.

**Ask First:** none expected — token values are either DESIGN.md's own or independently contrast-verified below.

**Never:**
- Do not touch anything under `backend/` or `frontend/src/context/AppContext.jsx` — zero overlap with the parallel auth work.
- Do not build the real Settings appearance-toggle UI — that's Epic 5. The `HealthPage` toggle is a throwaway dev affordance, not a designed component.
- Do not add a frontend test framework (vitest/RTL) in this story — out of scope; flag via review if a reviewer thinks it's needed.
- Do not introduce any hex value not already in DESIGN.md or computed in this spec (no new brand hues).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| No stored preference | `localStorage` empty, regardless of OS/browser dark-mode setting | App renders the light palette on first load | N/A |
| Explicit stored override | `localStorage` has `theme=dark` | Stored override wins on load, even with system set to light | N/A |
| Runtime toggle | User triggers the toggle affordance | `data-theme` flips, every token-driven surface updates with no reload | N/A |
| Reduced motion | `prefers-reduced-motion: reduce` set | Transitions/progress animations do not play | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/index.css` -- edit: full `@theme` token block (colors as swappable CSS vars, typography/spacing/radius as static Tailwind v4 theme keys); currently just `@import "tailwindcss";`
- `frontend/src/context/ThemeContext.jsx` -- new: `ThemeProvider` + `useTheme()`, defaults to light, `localStorage` persistence, sets `data-theme` on `<html>`
- `frontend/src/main.jsx` -- edit: wrap `<App />` in `ThemeProvider`
- `frontend/src/pages/HealthPage.jsx` -- edit: replace hardcoded `slate-*`/`red-*` classes with token-based utility classes; add a small temporary theme-toggle button
- `_bmad-output/planning-artifacts/ux-designs/.../DESIGN.md` -- read-only source of truth for all token values; no changes

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/index.css` -- define color tokens (`:root` light default + `[data-theme="dark"]` override), typography tokens (body/label/eyebrow/page-title/section-title/auth-title), spacing (`gutter`, `page-padding`, `section-padding` — Tailwind's default 1–10 scale already matches DESIGN.md's), radius (`sm`/`md`/`lg`/`xl`) -- single source of truth, no component hardcodes values
- [x] `frontend/src/index.css` -- status-pill and citation-chip tokens per the values fixed in Boundaries -- closes UX-DR21/UX-DR22
- [x] `frontend/src/index.css` -- focus-ring token + a `:focus-visible` rule applied globally to interactive elements -- closes UX-DR23
- [x] `frontend/src/index.css` -- wrap transition/animation rules in a `prefers-reduced-motion: no-preference` guard -- closes UX-DR28
- [x] `frontend/src/context/ThemeContext.jsx` -- `ThemeProvider`/`useTheme`, system-preference default, `localStorage` persistence, sets `data-theme` -- runtime switch plumbing (AD-5)
- [x] `frontend/src/main.jsx` -- mount `ThemeProvider` around `<App />` -- makes the context available app-wide
- [x] `frontend/src/pages/HealthPage.jsx` -- retrofit to tokens, add temporary toggle -- proves the token system end-to-end and makes AC5 (runtime switch) manually verifiable

**Acceptance Criteria:**
- Given DESIGN.md's palette/typography/spacing/radius values, when the token system is configured, then all are available as named tokens and no component hardcodes a raw value.
- Given the citation chip's accepted AA deviation, when citation tokens are configured, then they use `#4A7FE0`/`#D1EEFE` unchanged.
- Given the five ingestion states, when status-pill tokens are defined, then each of Uploaded/Extracting/Graphing/Ready/Failed has an explicit background-tint + text pair clearing 4.5:1.
- Given EXPERIENCE.md's focus-ring requirement, when the focus-ring token is defined, then it clears 3:1 against `bg`/`surface`/`surface-dark` and is visible on every interactive element in both themes.
- Given the app is rendering in one theme, when the theme is switched at runtime via `ThemeContext`, then every rendered surface updates immediately with no screen left theme-inconsistent.
- Given `prefers-reduced-motion` is set, when a transition/animation would play, then it is suppressed.

## Design Notes

Tailwind v4 CSS-first pattern for runtime-swappable color tokens — raw CSS vars per theme, `@theme` re-points at them so utility classes stay static while resolving dynamically:

```css
:root { --bg: #FFFFFF; --primary: #3861A8; }
:root[data-theme="dark"] { --bg: #1E222B; --primary: #5B8CFF; }
@theme inline { --color-bg: var(--bg); --color-primary: var(--primary); }
```

Typography/spacing/radius have no light/dark variants, so those are plain `@theme` keys (e.g. `--text-body: 13.5px;`, `--radius-lg: 12px;`), not swappable vars.

## Verification

**Commands:**
- `npm run dev` (from `frontend/`) -- expected: dev server starts, `HealthPage` renders using token-based classes, no console errors
- `npm run lint` (from `frontend/`) -- expected: passes

**Manual checks (if no CLI):**
- Toggle the temporary theme control on `HealthPage`: confirm background, text, and status-pill colors all update immediately with no reload.
- Toggle OS/browser dark mode with no stored override: confirm the app still loads light (system preference has no effect on the default).
- Enable `prefers-reduced-motion` in browser devtools: confirm no transition/animation plays.
- Zoom to 200%: confirm no horizontal scroll or clipping (carried forward as a standing constraint, nothing new to build here since there's only one page).

## Suggested Review Order

**Token system**

- Every DESIGN.md value as a swappable CSS var, light default + dark override.
  [`index.css:16`](../../frontend/src/index.css#L16)

- The five status-pill pairs, including the new `failed` pair's deliberately lower dark-mode opacity (`.06` vs `.16`) to clear AA.
  [`index.css:41`](../../frontend/src/index.css#L41)

- `--sky` gets an explicit dark override, mirroring `--citation-dark`, closing a gap the review caught.
  [`index.css:107`](../../frontend/src/index.css#L107)

- `@theme inline` re-points static utility classes at the runtime-swappable vars above.
  [`index.css:143`](../../frontend/src/index.css#L143)

- Global `:focus-visible` ring, reusing `primary`/`accent-dark` rather than inventing a new hue.
  [`index.css:212`](../../frontend/src/index.css#L212)

**Theme runtime**

- Inline script sets `data-theme` before first paint, closing the flash-of-wrong-theme bug three reviewers independently caught.
  [`index.html:9`](../../frontend/index.html#L9)

- `getStoredTheme`/`setThemeExplicit` now guard `localStorage` access instead of throwing in private-mode/sandboxed contexts.
  [`ThemeContext.jsx:10`](../../frontend/src/context/ThemeContext.jsx#L10)

- `data-theme` still gets applied post-mount too, so React state and the DOM never disagree after the inline script's first paint.
  [`ThemeContext.jsx:25`](../../frontend/src/context/ThemeContext.jsx#L25)

**Frontend integration (peripherals)**

- Retrofitted to token classes; temporary toggle and status-pill demo row are both marked as throwaway (TODO + `aria-hidden`).
  [`HealthPage.jsx:50`](../../frontend/src/pages/HealthPage.jsx#L50)

- `ThemeProvider` mounted around the whole app.
  [`main.jsx:9`](../../frontend/src/main.jsx#L9)
