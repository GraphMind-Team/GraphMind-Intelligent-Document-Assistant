// Shared color/type vocabulary for the knowledge-graph feature -- the
// single source both GraphCanvas.jsx (canvas fills, which need literal
// colors, not CSS custom properties) and GraphSummary.jsx (real DOM
// swatches) import, so switching between the canvas and "View as list"
// never shows two different color systems for the same entity/relationship
// types. Split out of GraphCanvas.jsx once GraphSummary needed the same
// values -- before that it was single-use and lived inline.
//
// Every hex below is a hand-derived, WCAG-verified step of one blue hue
// family (a deliberate design constraint: the graph should read as one
// visual system, not five unrelated type colors) -- computed against the
// literal `canvasBg`/`cardBg` values below via the standard relative-
// luminance formula, not eyeballed. Re-run that math before changing any
// value here; a value that looks fine on screen can still be a 3.9:1 that
// reads as 4.5+ at a glance.

// Canvas-only palette (drawNode/drawLinkLabel's fillStyle/strokeStyle
// need a literal color; a CSS custom property is meaningless to a 2D
// context). `ink` doubles as node-stroke, edge-label text/outline, and
// (via `--graph-ink` in index.css) the DOM chrome's primary text -- one
// value, reused everywhere it needs >=4.5:1 against `canvasBg`/`cardBg`,
// rather than a family of near-identical grays that could quietly drift
// apart.
//
// `canvasBg` is a deliberate, soft blue-white/deep-navy -- not the app's
// generic `--bg` -- so the graph reads as its own tinted "room" behind the
// nodes rather than sitting on the page's neutral ground. `link`'s alpha
// is bounded from below by WCAG 1.4.11 (an edge is graphical content
// required to understand the relationships this view exists to show):
// composited against `canvasBg`, light clears 3.67:1, dark clears 3.37:1.
export const PALETTE = {
  light: {
    canvasBg: '#F3F7FE',
    cardBg: '#F8FAFE',
    cardBorder: 'rgba(56, 97, 168, 0.22)',
    chipBg: 'rgba(56, 97, 168, 0.06)',
    chipBorder: 'rgba(56, 97, 168, 0.22)',
    ink: '#132340',
    link: 'rgba(34, 80, 143, 0.7)',
    nodeStroke: '#132340',
    accent: '#0EA5E9',
    // Darkened from `accent` for text use -- `accent` itself only clears
    // ~2.6:1 against `canvasBg`/`cardBg`, below the 4.5:1 small-text
    // minimum (mirrors index.css's own `--accent` vs `--link` split, same
    // reason: the vivid decorative value and the text-safe value are not
    // the same color). 5.28:1 against `canvasBg`, 5.43:1 against `cardBg`.
    accentText: '#0A6E99',
    glowShadow: 'rgba(19, 35, 64, 0.28)',
  },
  dark: {
    canvasBg: '#101B33',
    cardBg: '#141B2E',
    cardBorder: 'rgba(111, 168, 238, 0.25)',
    chipBg: 'rgba(111, 168, 238, 0.10)',
    chipBorder: 'rgba(111, 168, 238, 0.25)',
    ink: '#DCE6FA',
    link: 'rgba(111, 168, 238, 0.6)',
    nodeStroke: '#DCE6FA',
    accent: '#38BDF8',
    // Already >=4.5:1 against both surfaces in dark mode (8.0:1) --
    // unlike light mode, no separate darkened text variant is needed.
    accentText: '#38BDF8',
    glowShadow: 'rgba(0, 0, 0, 0.45)',
  },
}

export function paletteFor(theme) {
  return PALETTE[theme] ?? PALETTE.light
}

// Two-letter badges drawn inside each node -- the non-color signal
// AC6/UX-DR28 requires ("entity type... not carried by node colour
// alone"). The entity's name is drawn separately, beneath the node -- the
// badge alone isn't a substitute for it. Two letters is all that fits
// inside a 52px circle, which makes them opaque on their own, so the
// legend beneath the canvas and GraphSummary's grouped list both spell
// each one out.
const TYPE_BADGES = {
  Person: 'PE',
  Organization: 'OR',
  Project: 'PJ',
  Product: 'PD',
  Location: 'LO',
}

export function badgeFor(type) {
  return TYPE_BADGES[type] ?? type.slice(0, 2).toUpperCase()
}

// One five-step blue ramp, deep navy (Person) to pale sky (Location) --
// the types are peers, not a hierarchy of importance, but one shared hue
// family reads as one coherent system where five unrelated hues would
// read as arbitrary. Every fill/badge-text pair below was picked from a
// step where ONE of white or `ink` clears 4.5:1 decisively (>=5:1, not a
// hairline pass) -- the steps in between, where neither badge color
// reaches 4.5:1, were skipped entirely rather than shipped with a
// technically-failing badge.
//
// The two palest steps (Product, Location) sit under 3:1 against
// `canvasBg` on their own -- exactly the gap the original ramp already
// had (see PALETTE's own comment on `nodeStroke`) -- so `drawNode`'s
// `nodeStroke` outline is what carries WCAG 1.4.11's shape-
// distinguishability requirement for those two, same as before.
export const TYPE_COLORS = {
  light: {
    Person: { fill: '#0D366B', text: '#FFFFFF' },
    Organization: { fill: '#184F95', text: '#FFFFFF' },
    Project: { fill: '#256ABF', text: '#FFFFFF' },
    Product: { fill: '#6DA7EC', text: '#132340' },
    Location: { fill: '#B7D3F6', text: '#132340' },
  },
  dark: {
    Person: { fill: '#1E5FB0', text: '#FFFFFF' },
    Organization: { fill: '#256CC4', text: '#FFFFFF' },
    // Dark mode's badge text for the paler steps is the dark canvas
    // color itself (mirrors the light ramp's `ink`-on-pale-fill pattern,
    // just with the two ends swapped) -- a light `ink` value would fail
    // against these still-fairly-light dark-mode fills.
    Project: { fill: '#3987E5', text: '#101B33' },
    Product: { fill: '#5FA6EE', text: '#101B33' },
    Location: { fill: '#9AC9F5', text: '#101B33' },
  },
}

// A type outside OD-1's closed vocabulary can only reach here if the write
// path's own validation changes, but every caller should still draw it
// rather than crash on an undefined fill.
export function typeColorFor(theme, type) {
  const palette = paletteFor(theme)
  return (
    (TYPE_COLORS[theme] ?? TYPE_COLORS.light)[type] ?? {
      fill: palette.accent,
      text: palette.ink,
    }
  )
}

// Plain-language labels for OD-1's closed relationship-type vocabulary --
// the raw `WORKS_AT`/`PART_OF` enum values read as code, not the plain,
// declarative voice the rest of this app uses. A type outside the closed
// set (same reachability note as `badgeFor`) still renders, title-cased
// from its raw form, instead of crashing.
const RELATIONSHIP_LABELS = {
  WORKS_AT: 'Works at',
  SUPPLIES: 'Supplies',
  PART_OF: 'Part of',
  LOCATED_IN: 'Located in',
  RELATED_TO: 'Related to',
}

export function relationshipLabelFor(type) {
  const known = RELATIONSHIP_LABELS[type]
  if (known) return known
  const lower = type.replaceAll('_', ' ').toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}
