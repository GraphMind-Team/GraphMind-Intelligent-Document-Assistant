import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraphKapsule from 'force-graph'
import fromKapsule from 'react-kapsule'
// force-graph's own simulation library (already its dependency; listed
// explicitly in package.json now that this file imports it by name, same
// reasoning as `force-graph`/`react-kapsule` below).
import { forceCollide } from 'd3-force-3d'
import { useTheme } from '../../context/ThemeContext'
import GraphSummary from './GraphSummary'

// Built directly from `force-graph` (the vanilla 2D engine) and
// `react-kapsule` (the same wrapper `react-force-graph`'s own
// `ForceGraph2D` is built with internally) rather than `import {
// ForceGraph2D } from 'react-force-graph'` -- that package bundles its
// 2D/3D/VR/AR variants into one physical dist file sharing a single
// top-level scope. The 3D/VR/AR variants (from `3d-force-graph`/`-vr`/
// `-ar`) reference the globals `THREE`/`AFRAME` at module top level,
// expecting them loaded via a `<script>` tag rather than an ES import;
// since nothing in this app ever loads either, importing that combined
// package throws `ReferenceError`/`TypeError` at module-evaluation time
// and crashes the *entire* app on load (confirmed live: `AFRAME is not
// defined`, then `THREE is not defined`, then `THREE.Vector3 is not a
// constructor` even after stubbing both globals -- an unbounded chain of
// runtime assumptions, not one shallow guard). `force-graph` alone has
// no such dependency at all, so wrapping it directly sidesteps the
// problem instead of patching around it. `react-force-graph` is not a
// dependency here at all -- a deliberate deviation from the architecture
// spine's pinned library-family choice, recorded explicitly in
// spec-4-1's Design Notes (an unimported package left in `package.json`
// wouldn't "honor" that choice, it would just mislead the next reader
// into thinking it's in use).
//
// `methodNames` matters: react-kapsule omits those names from its
// prop-propagation pass and exposes them on the forwarded ref instead
// (see its `useImperativeHandle`), which is how `fitToView` below reaches
// the engine's imperative zoom API.
const ForceGraph2D = fromKapsule(ForceGraphKapsule, {
  methodNames: ['zoomToFit', 'zoom', 'getGraphBbox', 'd3Force', 'd3ReheatSimulation'],
})

// UX-DR11's literal spec.
const CANVAS_HEIGHT = 480
const MIN_NODE_DIAMETER = 52
const MAX_NODE_DIAMETER = 78
const MID_NODE_DIAMETER = 65 // used when every node has the same degree -- no ranking signal to normalize against

// Screen-pixel breathing room reserved around the fitted graph.
// `zoomToFit`'s bounding box covers each circle already -- `nodeVal`/
// `nodeRelSize` below teach the engine the radius `drawNode` really
// paints -- but not the entity name drawn *beneath* the circle, which the
// engine has no way to know about. So this only has to cover that name
// (~14px at the 10px font, plus its 4px offset), rounded up. It stays
// fixed in screen pixels while the overhang it covers is world-space and
// shrinks with the zoom, which makes it a safe over-estimate at every
// zoom this component reaches rather than only at k=1.
const FIT_PADDING = 20

// d3-force's defaults are tuned for the ~4px dots force-graph draws by
// default. UX-DR11's circles are 52-78px across -- an order of magnitude
// bigger -- so at the default charge and link distance every node lands
// inside its neighbours: labels collide, and the edges are real but
// buried underneath the overlapping fills. These scale the layout to the
// size actually being painted.
// Kept modest because `collide` below already guarantees the circles
// never overlap -- charge and link distance only have to set the resting
// spacing, and over-spreading them makes `fitToView` zoom a small graph
// out far enough to lose its labels.
const LINK_DISTANCE = 95
const CHARGE_STRENGTH = -140
// Clearance added to each node's collision radius, for the name drawn
// beneath it.
const LABEL_GUTTER = 16

// Below this on-screen size, drawing text costs legibility rather than
// adding any -- at a dense graph's fitted zoom the badge and name become
// unreadable smudges. Past the threshold the canvas carries shape and
// connectivity only, and GraphSummary (always visible, never zoomed)
// carries every name and type. Nothing is conveyed by node colour at any
// density -- every node is a single fill -- so AC6/UX-DR28 does not
// quietly depend on the badge surviving here.
const MIN_LEGIBLE_FONT_PX = 7

// Per press of the zoom buttons, and the bounds the wheel is held within.
const ZOOM_STEP = 1.4
const MIN_ZOOM = 0.15
const MAX_ZOOM = 4
const ZOOM_TRANSITION_MS = 180

// Canvas fillStyle needs a literal color, not a CSS custom property --
// these mirror index.css's `--primary`/`--on-primary`/`--bg` token values
// by hand (documentsClient.js's ALLOWED_EXTENSIONS comment notes the same
// kind of intentional hand-mirroring). Not read live via
// `getComputedStyle` because that would race `ThemeProvider`'s own
// `data-theme` attribute effect: React fires effects child-before-parent
// within a commit, so this component's effect would read the *previous*
// theme's attribute value on the very render a theme switch happens.
// `canvasBg` is `--bg`, not `--card-bg` -- DESIGN.md's `.graph-canvas`
// rule specifies `{colors.bg}` (#fff) as the fill (AC4), and the two only
// coincide in light mode; dark mode's `--bg` (#1E222B) and `--card-bg`
// (#262B35) are different colors.
// `link` is `--text2` at reduced alpha -- edges should read as subordinate
// to the nodes they connect, and force-graph's own default
// (`rgba(0,0,0,0.15)`) is all but invisible against dark mode's #1E222B
// canvas. The alpha is bounded from below by WCAG 1.4.11: an edge *is*
// the relationship this whole view exists to show, so it's a graphical
// object required to understand the content and owes 3:1 against the
// canvas fill. At the original 0.45/0.5 it composited to 2.19:1 (light)
// and 2.63:1 (dark) and failed; 0.65 in both themes gives 3.38:1 and
// 3.51:1 -- enough margin to survive a token nudge, still visibly
// lighter than both the node fills and the labels.
// `nodeStroke` exists for the same rule, applied to the circles: the
// light palette's two palest type fills (#48CAE4, #90E0EF) sit at 1.94:1
// and 1.49:1 on white, so the *shape* of a Product or Location node was
// carried by the drop shadow alone. No five steps of this blue ramp can
// all clear 3:1 against white, so the boundary carries it instead --
// `--text2` in both themes (8.36:1 light, 6.33:1 dark), neutral so it
// doesn't disturb the per-type ramp it outlines. Dark mode's fills
// already passed (4.69:1 and up); it gets the same outline anyway rather
// than a theme-conditional visual language.
const PALETTE = {
  light: {
    primary: '#3861A8',
    onPrimary: '#FFFFFF',
    canvasBg: '#FFFFFF',
    text: '#10131A',
    link: 'rgba(69, 78, 96, 0.65)',
    nodeStroke: '#454E60',
  },
  dark: {
    primary: '#5B8CFF',
    onPrimary: '#1E222B',
    canvasBg: '#1E222B',
    text: '#E4E7EC',
    link: 'rgba(154, 164, 181, 0.65)',
    nodeStroke: '#9AA4B5',
  },
}

// World units, like the radius -- so the outline thins out with the fit
// instead of thickening into a blob as a large graph zooms away.
const NODE_STROKE_WIDTH = 1.5

// Two-letter badges drawn inside each node -- the non-color signal
// AC6/UX-DR28 requires ("entity type... not carried by node colour
// alone"). The entity's name is drawn separately, beneath the node (see
// drawNode) -- the badge alone isn't a substitute for it. Two letters is
// all that fits inside a 52px circle, which makes them opaque on their
// own, so the legend below the canvas spells each one out; GraphSummary's
// grouped-by-type list is a third, always-visible way to see type.
const TYPE_BADGES = {
  Person: 'PE',
  Organization: 'OR',
  Project: 'PJ',
  Product: 'PD',
  Location: 'LO',
}

function badgeFor(type) {
  return TYPE_BADGES[type] ?? type.slice(0, 2).toUpperCase()
}

// Mirrors index.css's `--graph-*` tokens, for the same reason PALETTE
// above does: a canvas fillStyle needs a literal, not a custom property.
// `text` is the badge colour drawn on that fill -- white only where the
// fill is dark enough to carry it at 4.5:1, since the badge is 10.5px
// bold and gets no large-text exemption.
const TYPE_COLORS = {
  light: {
    Person: { fill: '#023E8A', text: '#FFFFFF' },
    Organization: { fill: '#0077B6', text: '#FFFFFF' },
    Project: { fill: '#0096C7', text: '#10131A' },
    Product: { fill: '#48CAE4', text: '#10131A' },
    Location: { fill: '#90E0EF', text: '#10131A' },
  },
  dark: {
    Person: { fill: '#0096C7', text: '#1E222B' },
    Organization: { fill: '#00B4D8', text: '#1E222B' },
    Project: { fill: '#48CAE4', text: '#1E222B' },
    Product: { fill: '#90E0EF', text: '#1E222B' },
    Location: { fill: '#ADE8F4', text: '#1E222B' },
  },
}

// A type outside OD-1's closed vocabulary can only reach here if the write
// path's own validation changes, but the canvas should still draw it
// rather than crash on an undefined fill.
function typeColorFor(theme, type) {
  const palette = PALETTE[theme] ?? PALETTE.light
  return (
    (TYPE_COLORS[theme] ?? TYPE_COLORS.light)[type] ?? {
      fill: palette.primary,
      text: palette.onPrimary,
    }
  )
}

function diameterFor(degree, minDegree, maxDegree) {
  if (minDegree === maxDegree) return MID_NODE_DIAMETER
  const ratio = (degree - minDegree) / (maxDegree - minDegree)
  return MIN_NODE_DIAMETER + ratio * (MAX_NODE_DIAMETER - MIN_NODE_DIAMETER)
}

// A name drawn at full length has no upper bound -- "Northbridge
// Logistics" already nearly spans two node-widths at MIN_NODE_DIAMETER,
// and nothing stops it running into a neighbour placed close by (`collide`
// keeps *circles* apart, not the text drawn outside them). Truncated with
// an ellipsis to `maxWidth` (world units, matching drawNode's other
// undivided-by-globalScale measurements) rather than hidden -- the start
// of a name is usually enough to tell entities apart, and the full name is
// always available in GraphSummary regardless of canvas width.
function truncateToWidth(ctx, text, maxWidth) {
  if (ctx.measureText(text).width <= maxWidth) return text
  const ellipsis = '…'
  let end = text.length
  while (end > 0 && ctx.measureText(text.slice(0, end) + ellipsis).width > maxWidth) {
    end -= 1
  }
  return end > 0 ? text.slice(0, end) + ellipsis : ellipsis
}

// No ResizeObserver here (unavailable in this project's jsdom test
// environment, and this component's own test mocks `force-graph`/
// `react-kapsule` themselves, not the surrounding measurement logic) -- a plain `resize`
// listener plus an initial measurement covers window/layout resizes,
// which is the only way this container's width actually changes today
// (no split-pane or collapsible sidebar resizes it independently).
function useContainerWidth(ref) {
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const el = ref.current
    if (!el) return undefined
    const measure = () => setWidth(el.clientWidth)
    measure()
    window.addEventListener('resize', measure)
    return () => window.removeEventListener('resize', measure)
  }, [ref])
  return width
}

// Read-only knowledge-graph canvas (Story 4.1, UX-DR11). `force-graph`
// lays entities out with its physics engine, but every pointer
// interaction is disabled below -- no click-to-query, no drag, no
// zoom/pan, and (since `enablePointerInteraction` is off) no hover reveal
// either. That's what makes "if nodes carry no interaction at all, that is
// stated explicitly" (AC7) literally true rather than a restriction
// bolted onto an otherwise-interactive canvas -- GraphSummary alongside it
// states this in plain visible text. The one thing that does move the view
// is `fitToView`, programmatically: disabling the *user's* zoom is the AC,
// leaving part of the graph permanently unreachable is not.
//
// Assumes `graph.nodes` is non-empty -- GraphPage.jsx renders its own
// empty-state message instead of this component when there are no
// entities at all.
export default function GraphCanvas({ graph }) {
  const { theme } = useTheme()
  const containerRef = useRef(null)
  const graphRef = useRef(null)
  const width = useContainerWidth(containerRef)

  const palette = PALETTE[theme] ?? PALETTE.light
  const { nodes, edges } = graph

  const degrees = nodes.map((node) => node.degree)
  const minDegree = degrees.length ? Math.min(...degrees) : 0
  const maxDegree = degrees.length ? Math.max(...degrees) : 0

  const presentTypes = useMemo(
    () => [...new Set(nodes.map((node) => node.type))].sort((a, b) => a.localeCompare(b)),
    [nodes],
  )

  const radiusFor = useCallback(
    (node) => diameterFor(node.degree, minDegree, maxDegree) / 2,
    [minDegree, maxDegree],
  )

  // Teaches the engine the radius `drawNode` actually paints. Everything
  // force-graph computes from node size -- its bounding box (so
  // `fitToView` fits the circles, not their centres) and where a
  // directional arrow stops -- otherwise assumes the ~4px default dot.
  // `nodeRelSize` 1 makes `sqrt(nodeVal) * nodeRelSize` collapse to
  // exactly the painted radius.
  const nodeVal = useCallback((node) => radiusFor(node) ** 2, [radiusFor])

  // A function, not the colour string: force-graph reads a string accessor
  // as the name of a property on the link object, not as a literal colour.
  const linkColor = useCallback(() => palette.link, [palette.link])

  // Without this, nothing ever changes the canvas transform: pointer zoom
  // and pan are disabled, and `force-graph` never fits the view on its own
  // (`zoomToFit` exists purely as an imperative method it does not call).
  // The visible world region would stay exactly the canvas's pixel box, so
  // a graph whose layout is larger than 480px tall -- which the d3-force
  // defaults reach at roughly thirty nodes, well under this story's
  // 150-node cap -- would render partly outside it with no pan, zoom or
  // scroll to reach the rest.
  //
  // Clamped at k=1 rather than fitted unconditionally: a graph that
  // already fits should render at UX-DR11's specified node sizes, not be
  // magnified past them just because there is room.
  // Once someone has zoomed deliberately, an automatic refit (a window
  // resize, say) would yank the view out from under them. The Fit button
  // is how they hand control back.
  const userAdjustedZoomRef = useRef(false)

  const fitToView = useCallback(() => {
    const engine = graphRef.current
    if (!engine) return

    // The bounding-box guard is load-bearing, not defensive padding. On
    // the first commit the engine is mounted but the simulation has not
    // placed anything yet, so the box is `NaN` -- and `zoomToFit` would
    // hand that straight to d3-zoom's `scaleTo`, which is *relative* to
    // the current transform. One `NaN` there poisons the transform
    // permanently: every later fit, including the good one at
    // `onEngineStop`, multiplies through it and stays `NaN`, leaving a
    // blank canvas.
    const bbox = engine.getGraphBbox()
    const isMeasured =
      bbox && [...bbox.x, ...bbox.y].every((coordinate) => Number.isFinite(coordinate))
    if (!isMeasured) return

    engine.zoomToFit(0, FIT_PADDING)
    const fitted = engine.zoom()
    // `> 1` also catches the degenerate single-node box, where a zero-width
    // span sends `zoomToFit`'s own division to force-graph's 1e12 ceiling.
    if (Number.isFinite(fitted) && fitted > 1) engine.zoom(1)
  }, [])

  const resetView = useCallback(() => {
    userAdjustedZoomRef.current = false
    fitToView()
  }, [fitToView])

  const stepZoom = useCallback((factor) => {
    const engine = graphRef.current
    if (!engine) return
    const current = engine.zoom()
    if (!Number.isFinite(current)) return
    userAdjustedZoomRef.current = true
    const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, current * factor))
    engine.zoom(next, ZOOM_TRANSITION_MS)
  }, [])

  // `force-graph` mutates the objects it's given (adds `x`/`y`/`vx`/`vy`
  // for the simulation) -- copied here so it never mutates `graph` itself,
  // which the caller (GraphPage) still owns.
  const graphData = useMemo(
    () => ({
      nodes: nodes.map((node) => ({ ...node })),
      links: edges.map((edge) => ({ ...edge })),
    }),
    [nodes, edges],
  )

  // Scale the simulation to the circles being drawn. `collide` is what
  // actually guarantees they stop landing on top of each other -- charge
  // and link distance only make crowding less likely, and a graph where
  // two nodes overlap hides the edge between them entirely.
  useEffect(() => {
    const engine = graphRef.current
    if (!engine) return
    engine.d3Force('charge').strength(CHARGE_STRENGTH)
    engine.d3Force('link').distance(LINK_DISTANCE)
    engine.d3Force(
      'collide',
      forceCollide((node) => radiusFor(node) + LABEL_GUTTER),
    )
    engine.d3ReheatSimulation()
    // `width` is a real dependency, not noise: ForceGraph2D is not
    // rendered at all until the container has been measured, so on the
    // first pass there is no engine to configure and this has to run again
    // once there is.
  }, [radiusFor, graphData, width])

  // `onEngineStop` covers the layout settling, which is when the fit
  // matters most. This covers the two cases that change what has to fit
  // without restarting the engine: a window resize narrowing the canvas,
  // and new graph data arriving after the simulation has already cooled.
  useEffect(() => {
    if (userAdjustedZoomRef.current) return
    fitToView()
  }, [fitToView, width, graphData])

  const handleEngineStop = useCallback(() => {
    if (userAdjustedZoomRef.current) return
    fitToView()
  }, [fitToView])

  // Wheel zoom and drag-pan are both force-graph's own
  // (`enableZoomInteraction`/`enablePanInteraction`); these only record
  // that one happened, so a later resize does not refit over the view the
  // user deliberately moved to.
  //
  // Deliberately *not* force-graph's `onZoom` callback, which would be the
  // obvious hook: force-graph calls `zoom.scaleTo` itself on every data
  // change (its `ZOOM2NODES_FACTOR / cbrt(N)` heuristic), and d3-zoom
  // fires the same `zoom` event for that as for a user gesture -- so
  // `onZoom` would latch this ref on mount and auto-fit would never run
  // again. Listening for the input events instead keeps "the user moved
  // the view" and "the engine moved the view" distinguishable.
  const markUserViewChange = useCallback(() => {
    userAdjustedZoomRef.current = true
  }, [])

  // `buttons > 0` is what separates a pan from a plain mouse-over: it's a
  // bitmask of the buttons currently held, so this fires on drag only, and
  // (unlike a pointerdown/pointerup pair) can't get stuck believing a
  // button is still down after a release that happened off-element.
  // Touch pointers report `buttons` 1 while in contact, so a finger drag
  // counts too.
  const handlePointerMove = useCallback(
    (event) => {
      if (event.buttons > 0) markUserViewChange()
    },
    [markUserViewChange],
  )

  function drawNode(node, ctx, globalScale) {
    // Drawn in world units, deliberately *not* divided by `globalScale`.
    // At the unzoomed k=1 a small graph renders at, that is literally
    // UX-DR11's 52-78px diameter and 10.5px/700 label. When `fitToView`
    // zooms out to bring a large graph inside the 480px box, the nodes
    // shrink with it -- which is the whole point: constant-screen-size
    // nodes would just re-overflow the canvas the fit was meant to fix.
    const diameter = diameterFor(node.degree, minDegree, maxDegree)
    const radius = diameter / 2

    ctx.save()
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
    // Shadow blur/offset are specified in device space and are *not*
    // affected by the canvas transform, so these stay the literal
    // `0 2px 6px` from DESIGN.md's elevation rule rather than being
    // scaled.
    const typeColor = typeColorFor(theme, node.type)

    ctx.shadowColor = 'rgba(10, 46, 99, 0.25)'
    ctx.shadowBlur = 6
    ctx.shadowOffsetY = 2
    ctx.fillStyle = typeColor.fill
    ctx.fill()

    // The boundary that makes a pale fill a distinguishable object at all
    // (WCAG 1.4.11 -- see PALETTE.nodeStroke). Shadow cleared first so the
    // outline doesn't paint a second copy of it on top of the fill's.
    ctx.shadowColor = 'transparent'
    ctx.shadowBlur = 0
    ctx.shadowOffsetY = 0
    ctx.lineWidth = NODE_STROKE_WIDTH
    ctx.strokeStyle = palette.nodeStroke
    ctx.stroke()
    ctx.restore()

    const fontSize = 10.5
    const nameFontSize = 10
    // Both labels vanish together below the legibility floor -- a visible
    // badge over an illegible name would read as though the name were
    // missing rather than deliberately withheld.
    if (Math.min(fontSize, nameFontSize) * globalScale < MIN_LEGIBLE_FONT_PX) return

    ctx.font = `700 ${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = typeColor.text
    ctx.fillText(badgeFor(node.type), node.x, node.y)

    // Entity name, drawn beneath the node rather than inside it -- the
    // circle is too small at MIN_NODE_DIAMETER to fit both the type badge
    // and a full name legibly. Truncated to roughly two node-widths so a
    // long name doesn't run into whatever's drawn next to it.
    ctx.font = `500 ${nameFontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = palette.text
    ctx.fillText(truncateToWidth(ctx, node.name, MAX_NODE_DIAMETER * 2), node.x, node.y + radius + 4)
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={() => stepZoom(1 / ZOOM_STEP)}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-text"
        >
          <span aria-hidden="true">−</span>
          <span className="sr-only">Zoom out</span>
        </button>
        <button
          type="button"
          onClick={() => stepZoom(ZOOM_STEP)}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-text"
        >
          <span aria-hidden="true">+</span>
          <span className="sr-only">Zoom in</span>
        </button>
        <button
          type="button"
          onClick={resetView}
          className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-semibold text-text"
        >
          Fit
        </button>
      </div>
      <div
        ref={containerRef}
        role="img"
        // Short and generic on purpose -- GraphSummary immediately below
        // is the real accessible content (AC7) and already states the
        // entity/relationship counts and the read-only, zoomable nature of
        // the view in visible text. Restating all of that here would have
        // a screen reader announce the same sentence twice back to back;
        // this just identifies what kind of region a screen-reader user
        // has landed on.
        aria-label="Knowledge graph visualization"
        className="overflow-hidden rounded-xl border border-border bg-bg"
        style={{ height: CANVAS_HEIGHT }}
        onWheel={markUserViewChange}
        onPointerMove={handlePointerMove}
      >
        {width > 0 && (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={width}
            height={CANVAS_HEIGHT}
            backgroundColor={palette.canvasBg}
            nodeCanvasObject={drawNode}
            nodeVal={nodeVal}
            nodeRelSize={1}
            nodeLabel={null}
            linkColor={linkColor}
            // Relationships are directed (a Person WORKS_AT an
            // Organization, not the reverse); an undecorated line loses
            // that. Placed at the target end, which lands just outside the
            // target circle now that `nodeVal` tells the engine how big
            // these nodes really are.
            linkDirectionalArrowLength={9}
            linkDirectionalArrowRelPos={1}
            onEngineStop={handleEngineStop}
            minZoom={MIN_ZOOM}
            maxZoom={MAX_ZOOM}
            // AC5's read-only rule is about the *graph*: no click-to-query,
            // no drag-to-rearrange, no editing. Moving the viewport is none
            // of those, and at 150 capped entities in a 480px box a fitted
            // view alone is not readable -- so wheel zoom and pan are on,
            // while node drag and all pointer hit-testing stay off.
            enableNodeDrag={false}
            enablePointerInteraction={false}
            enableZoomInteraction={true}
            enablePanInteraction={true}
          />
        )}
      </div>
      {/* The badge drawn inside each circle is two letters -- unreadable
          as a type name on its own. This spells out only the types
          actually on the canvas, so it stays short. */}
      <ul
        aria-label="Entity type key"
        className="mt-2 flex list-none flex-wrap gap-x-4 gap-y-1 p-0 text-sm text-text2"
      >
        {presentTypes.map((type) => {
          const typeColor = typeColorFor(theme, type)
          return (
            <li key={type} className="flex items-center gap-1.5">
              {/* The badge sits on its own colour, so the key shows the
                  same pairing the canvas does. aria-hidden because the
                  badge letters and the type name next to it already say
                  everything this conveys. */}
              <span
                aria-hidden="true"
                className="inline-flex h-5 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                style={{ backgroundColor: typeColor.fill, color: typeColor.text }}
              >
                {badgeFor(type)}
              </span>
              <span className="sr-only">{badgeFor(type)}</span> {type}
            </li>
          )
        })}
      </ul>
      <GraphSummary nodes={nodes} edges={edges} />
    </div>
  )
}
