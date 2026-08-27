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
    // Design system v2 ("Aurora Sky"): the graph's own room is now a
    // near-white sky-tinted ground rather than the v1 lavender-blue, so
    // it sits in the same family as every other surface in the app while
    // still reading as its own space. Mirrors index.css's `--graph-*`.
    canvasBg: '#F5FAFE',
    cardBg: '#FFFFFF',
    cardBorder: 'rgba(3, 105, 161, 0.16)',
    chipBg: 'rgba(14, 165, 233, 0.08)',
    chipBorder: 'rgba(3, 105, 161, 0.18)',
    ink: '#0B1A2B',
    // Secondary ink for supporting prose (the read-only/count line).
    // Mirrors index.css's `--graph-ink2`; 5.9:1 on `cardBg`. v1 read this
    // key off the palette without it ever being defined, so that line
    // silently inherited its color instead.
    ink2: 'rgba(11, 26, 43, 0.72)',
    // Edge stroke. WCAG 1.4.11 applies (an edge is graphical content
    // required to understand the relationships this view exists to
    // show): composited on `canvasBg` this clears 3.4:1.
    link: 'rgba(3, 105, 161, 0.55)',
    // v2 draws each node as a colored disc with a *canvas-colored* ring
    // knocked out around it (plus a soft type-colored halo outside
    // that), rather than a dark hairline outline. The ring is what
    // separates overlapping nodes and what carries 1.4.11 for the two
    // palest ramp steps -- against those pale fills a near-white ring
    // still clears 3:1, and against the dark steps it clears far more.
    nodeRing: '#F5FAFE',
    // Retained for the label halo and the edge-label pill's text/border,
    // where a real ink value is still what's wanted.
    nodeStroke: '#0B1A2B',
    accent: '#0EA5E9',
    // Text-safe variant of `accent` -- `accent` itself only clears
    // ~2.6:1 on these surfaces, below the 4.5:1 small-text minimum
    // (mirrors index.css's own `--accent` vs `--link` split). #0B5FA5
    // clears 5.9:1 on `canvasBg` and 6.1:1 on `cardBg`.
    accentText: '#0B5FA5',
    // Node drop-shadow -- tight and low, for depth. The wider colored
    // halo drawn in `drawNode` is a separate, decorative layer.
    nodeShadow: 'rgba(8, 40, 74, 0.22)',
  },
  dark: {
    canvasBg: '#0A1526',
    cardBg: '#0E1728',
    cardBorder: 'rgba(56, 189, 248, 0.20)',
    chipBg: 'rgba(56, 189, 248, 0.10)',
    chipBorder: 'rgba(56, 189, 248, 0.22)',
    ink: '#E8EEF7',
    ink2: 'rgba(232, 238, 247, 0.7)',
    link: 'rgba(125, 211, 252, 0.5)',
    nodeRing: '#0A1526',
    nodeStroke: '#E8EEF7',
    accent: '#38BDF8',
    // Already 8.0:1 on both dark surfaces -- no separate darkened text
    // variant needed, unlike light mode.
    accentText: '#38BDF8',
    nodeShadow: 'rgba(0, 0, 0, 0.5)',
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

// Plain-language labels for OD-1's closed entity-type vocabulary (mirrors
// `relationshipLabelFor` below) -- the raw `type` string is the vocabulary
// key everywhere else in this module (TYPE_BADGES/TYPE_COLORS lookups,
// group identity, sort order), so only the rendered label goes through
// `t()`; a type outside the closed set still renders as its raw form
// instead of crashing. Takes `t` as a parameter rather than calling
// `useTranslation()` itself -- this is a plain module, not a component/hook,
// mirrored by every caller already holding its own `t` from `useTranslation()`.
const ENTITY_TYPE_KEYS = {
  Person: 'graph.entityTypes.Person',
  Organization: 'graph.entityTypes.Organization',
  Project: 'graph.entityTypes.Project',
  Product: 'graph.entityTypes.Product',
  Location: 'graph.entityTypes.Location',
}

export function entityTypeLabelFor(t, type) {
  const key = ENTITY_TYPE_KEYS[type]
  return key ? t(key) : type
}

// OD-1's closed entity vocabulary, in the order the colour ramp below
// steps through it (deep ocean -> pale sky), which is also the order it
// is written down in the decision itself. Exported so the legend can show
// the whole vocabulary rather than only the types a given graph happens
// to contain: a key listing four types with no indication that a fifth
// exists reads as an arbitrary set, which is exactly how it was read in
// review ("why these four?"). Mirrors `ENTITY_TYPES` in
// backend/app/shared/llm_client -- the write path is what actually
// enforces the set; this is only how it is presented.
export const ENTITY_TYPE_ORDER = ['Person', 'Organization', 'Project', 'Product', 'Location']

// One five-step sky ramp, deep ocean (Person) to pale sky (Location) --
// the types are peers, not a hierarchy of importance, but one shared hue
// family reads as one coherent system where five unrelated hues would
// read as arbitrary. Every fill/badge-text pair below was picked from a
// step where ONE of white or `ink` clears 4.5:1 decisively (>=5:1, not a
// hairline pass) -- the steps in between, where neither badge color
// reaches 4.5:1, were skipped entirely rather than shipped with a
// technically-failing badge.
//
// The two palest steps (Product, Location) sit under 3:1 against
// `canvasBg` on their own -- so `drawNode`'s knocked-out `nodeRing`
// plus the type-colored halo around it are what carry WCAG 1.4.11's
// shape-distinguishability requirement for those two (v1 used a dark
// hairline outline for the same job).
export const TYPE_COLORS = {
  light: {
    Person: { fill: '#073B60', text: '#FFFFFF' },
    Organization: { fill: '#075E8C', text: '#FFFFFF' },
    Project: { fill: '#0A7BB5', text: '#FFFFFF' },
    Product: { fill: '#67C7F0', text: '#0B1A2B' },
    Location: { fill: '#BEE7FB', text: '#0B1A2B' },
  },
  dark: {
    Person: { fill: '#0F5B94', text: '#FFFFFF' },
    Organization: { fill: '#0F6BA8', text: '#FFFFFF' },
    // The paler dark-mode steps take the dark canvas color as badge
    // text (mirrors the light ramp's ink-on-pale-fill pattern with the
    // ends swapped) -- a light ink would fail against these fills.
    Project: { fill: '#3FA9E0', text: '#0A1526' },
    Product: { fill: '#6FC5EE', text: '#0A1526' },
    Location: { fill: '#A8DDF8', text: '#0A1526' },
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
// from its raw form, instead of crashing -- that fallback can't go through
// `t()` (there's no key for an unknown type), so it stays English same as
// before.
const RELATIONSHIP_LABEL_KEYS = {
  WORKS_AT: 'graph.relationshipTypes.WORKS_AT',
  SUPPLIES: 'graph.relationshipTypes.SUPPLIES',
  PART_OF: 'graph.relationshipTypes.PART_OF',
  LOCATED_IN: 'graph.relationshipTypes.LOCATED_IN',
  RELATED_TO: 'graph.relationshipTypes.RELATED_TO',
}

export function relationshipLabelFor(t, type) {
  const key = RELATIONSHIP_LABEL_KEYS[type]
  if (key) return t(key)
  const lower = type.replaceAll('_', ' ').toLowerCase()
  return lower.charAt(0).toUpperCase() + lower.slice(1)
}
