import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ForceGraphKapsule from 'force-graph'
import fromKapsule from 'react-kapsule'
// force-graph's own simulation library (already its dependency; listed
// explicitly in package.json now that this file imports it by name, same
// reasoning as `force-graph`/`react-kapsule` below).
import { forceCollide } from 'd3-force-3d'
import { useTheme } from '../../context/ThemeContext'
import GraphSummary from './GraphSummary'
import { badgeFor, paletteFor, relationshipLabelFor, typeColorFor } from './graphTheme'

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
// default; these scale the layout to the 52-78px circles actually
// painted. Both scale with node count, not fixed constants: a flat
// charge/link-distance looks fine for a handful of nodes and then
// visibly collapses in on itself as a real account's graph grows past
// ~8-10 entities -- more nodes means more simultaneous pairwise link
// attractions pulling everything toward the centre, and a constant
// per-node repulsion can't keep up (confirmed against a real 8-entity
// account graph: `collide` alone kept circles from sitting exactly on
// top of each other, but did nothing to stop the layout as a whole from
// crowding into a dense, edge-crossing clump). More entities now push
// apart harder and rest farther apart, so density stays roughly constant
// as the graph grows instead of compounding.
//
// Capped in both directions: the lower bound keeps a small graph from
// over-spreading (which would make `fitToView` zoom out far enough to
// lose the labels UX-DR11 specifies); the upper bound is deliberately
// reached well before this story's 150-node ceiling -- past ~25-30 nodes,
// *more* per-node force stops helping (more circles need more room
// regardless of how hard they repel each other) and only makes the fit
// zoom shrink faster for no legibility gain, so growth is capped rather
// than left to keep compounding into ever-more-extreme values.
//
// Verified by actually running this exact force setup (d3-force-3d,
// `node -e` against a synthetic graph, not eyeballed) at several node
// counts and checking the resulting bounding box against `MIN_ZOOM`
// below -- an earlier, more aggressive version of these constants pushed
// the required fit zoom below `MIN_ZOOM` once graphs passed ~40-50 nodes,
// which is exactly what "Fit" (and the auto-fit-on-load this same
// function drives) not working for a real, larger account graph looks
// like: the zoom clamps at the floor and can't actually show the whole
// layout. `MIN_ZOOM` itself is set low enough to cover this story's own
// 150-node ceiling with headroom, so the *cap* here only has to keep the
// force parameters themselves from spiralling into unreasonable values,
// not carry the large-graph case by itself.
const LINK_DISTANCE_BASE = 130
const LINK_DISTANCE_PER_NODE = 4
const MAX_LINK_DISTANCE = 220
const CHARGE_STRENGTH_BASE = -240
const CHARGE_STRENGTH_PER_NODE = -14
const MAX_CHARGE_STRENGTH_MAGNITUDE = 620

function linkDistanceFor(nodeCount) {
  return Math.min(MAX_LINK_DISTANCE, LINK_DISTANCE_BASE + nodeCount * LINK_DISTANCE_PER_NODE)
}

function chargeStrengthFor(nodeCount) {
  return Math.max(-MAX_CHARGE_STRENGTH_MAGNITUDE, CHARGE_STRENGTH_BASE + nodeCount * CHARGE_STRENGTH_PER_NODE)
}
// Clearance added to each node's collision radius, for the name drawn
// beneath it -- generous enough that a neighbouring node's glow halo
// (GLOW_RADIUS_MULTIPLIER below) and a curved edge's label chip both clear
// this node's own name rather than crossing through it.
const LABEL_GUTTER = 30

// Below this on-screen size, drawing text costs legibility rather than
// adding any -- at a dense graph's fitted zoom the badge and name become
// unreadable smudges. Past the threshold the canvas carries shape and
// connectivity only, and GraphSummary (always visible, never zoomed)
// carries every name and type. Nothing is conveyed by node colour at any
// density -- every node is a single fill -- so AC6/UX-DR28 does not
// quietly depend on the badge surviving here.
const MIN_LEGIBLE_FONT_PX = 7

// The relationship-type chip drawn on each edge -- smaller than the node
// labels (10.5px badge / 10px name) since there are more edges than nodes
// in a typical graph and this is supporting detail, not the primary
// content. Gated behind the same `MIN_LEGIBLE_FONT_PX` floor as the node
// labels above, for the same reason.
const LINK_LABEL_FONT_SIZE = 8.5
const LINK_LABEL_PADDING_X = 6
const LINK_LABEL_PADDING_Y = 3

// Per press of the zoom buttons, and the bounds the wheel is held within.
// `MIN_ZOOM` also bounds what `fitToView` (`zoomToFit`) can ever reach --
// `zoomToFit` computes whatever scale actually fits the current graph
// bounding box, and d3-zoom clamps that computed value to this floor
// regardless of whether the change is a user gesture or a programmatic
// call. Set low enough (with real headroom) that this story's 150-node
// ceiling can still reach its own required fit scale -- verified by
// simulation (see `chargeStrengthFor`'s comment) at roughly 0.06 for a
// dense 150-node graph.
const ZOOM_STEP = 1.4
const MIN_ZOOM = 0.035
const MAX_ZOOM = 4
const ZOOM_TRANSITION_MS = 180

// World units, like the radius -- so the outline thins out with the fit
// instead of thickening into a blob as a large graph zooms away.
const NODE_STROKE_WIDTH = 1.5

// The soft colored bloom drawn behind every node (drawNode's glow pass) --
// a second, larger, low-alpha fill of the same circle, colored with the
// node's own type fill so each type's glow reads as that type's hue, not
// one uniform highlight. World units and unitless alpha, like the crisp
// circle drawn on top of it, so both shrink together as the fit zooms out.
const GLOW_RADIUS_MULTIPLIER = 1.7
const GLOW_ALPHA = 0.22
const GLOW_BLUR = 16

function diameterFor(degree, minDegree, maxDegree) {
  if (minDegree === maxDegree) return MID_NODE_DIAMETER
  const ratio = (degree - minDegree) / (maxDegree - minDegree)
  return MIN_NODE_DIAMETER + ratio * (MAX_NODE_DIAMETER - MIN_NODE_DIAMETER)
}

// OD-1's closed relationship-type set means two *different* types between
// the exact same pair of entities (e.g. a specific WORKS_AT alongside a
// generic RELATED_TO fallback the extractor also produced) is a real,
// expected shape -- not a data error. Left as overlapping straight lines,
// their labels would land exactly on top of each other, unreadable. This
// bows each edge in such a group apart from the others by mutating a
// `curvature` field onto the link objects `graphData` already copies (so
// `graph`, the caller's own object, is never touched) -- a lone edge
// between a pair is left at the implicit `curvature` of `undefined`
// (read as 0 by `linkCurvature`/`quadraticMidpoint` below), staying a
// plain straight line rather than curving for no reason.
const PARALLEL_EDGE_CURVATURE_STEP = 0.22

function assignParallelEdgeCurvature(links) {
  const groups = new Map()
  for (const link of links) {
    const key = [link.source, link.target].sort().join('::')
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key).push(link)
  }
  for (const group of groups.values()) {
    const n = group.length
    if (n < 2) continue
    // Curvature is relative to a link's own source->target direction, so
    // without this the pair's two directions (a link genuinely running
    // A->B alongside one running B->A) would bow in opposite senses and
    // could still land back on top of each other instead of spreading
    // apart. Normalizing every offset against one canonical order for the
    // pair keeps the whole group bowing the same way.
    const canonicalFirst = [group[0].source, group[0].target].sort()[0]
    group.forEach((link, i) => {
      const offset = (i - (n - 1) / 2) * PARALLEL_EDGE_CURVATURE_STEP
      link.curvature = link.source === canonicalFirst ? offset : -offset
    })
  }
  return links
}

// Mirrors force-graph's own internal control-point formula exactly (its
// `calcLinkControlPoints`) so a curved edge's label lands on the curve it
// actually draws, not the straight chord between the two nodes. Recomputed
// here rather than read off the engine's own `link.__controlPoints` (set
// during its paint pass) because that field is a private implementation
// detail, not public API.
//
// The point returned is the curve's true midpoint (t=0.5 on the quadratic
// bezier through start/control/end), not merely "halfway between the two
// control-point formula's inputs" -- for a quadratic bezier those are the
// same thing only when the curve is a straight line.
function quadraticMidpoint(start, end, curvature) {
  if (!curvature) {
    return { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 }
  }
  const length = Math.hypot(end.x - start.x, end.y - start.y)
  const angle = Math.atan2(end.y - start.y, end.x - start.x)
  const distance = length * curvature
  const controlX = (start.x + end.x) / 2 + distance * Math.cos(angle - Math.PI / 2)
  const controlY = (start.y + end.y) / 2 + distance * Math.sin(angle - Math.PI / 2)
  return {
    x: 0.25 * start.x + 0.5 * controlX + 0.25 * end.x,
    y: 0.25 * start.y + 0.5 * controlY + 0.25 * end.y,
  }
}

// A stadium/pill outline built from two half-circle arcs (`ctx.arc` twice)
// rather than `ctx.roundRect` -- keeps this on the same small set of 2D
// context primitives the rest of this file already relies on (and that
// this component's own tests already mock), instead of a newer canvas
// method not universally available. Two `arc` calls with no `moveTo`
// between them still connect correctly: per the canvas spec, a path
// command issued mid-path draws an implicit straight line to its own
// start point first, which is exactly the pill's two straight sides.
function pillPath(ctx, centerX, centerY, width, height) {
  const radius = height / 2
  const left = centerX - width / 2 + radius
  const right = centerX + width / 2 - radius
  ctx.beginPath()
  ctx.arc(left, centerY, radius, Math.PI / 2, -Math.PI / 2)
  ctx.arc(right, centerY, radius, -Math.PI / 2, Math.PI / 2)
  ctx.closePath()
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

  const palette = paletteFor(theme)
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

  // Reads the `curvature` field `assignParallelEdgeCurvature` sets inside
  // `graphData` below. `?? 0` covers the common case (a lone edge between
  // its pair, left with no `curvature` field at all) explicitly, rather
  // than relying on `undefined` happening to be falsy wherever this value
  // is later used arithmetically.
  const linkCurvature = useCallback((link) => link.curvature ?? 0, [])

  // A literal `'after'` string prop would be misread: force-graph treats a
  // *string* accessor as a property name to look up per-link (`link.after`,
  // always `undefined` here), not a constant -- only a function reliably
  // returns the same mode for every link. 'after' specifically because
  // `drawLinkLabel` needs the line already painted beneath it, not to draw
  // first and have the line stroke straight through its own label (the
  // directional arrowhead paints in its own separate pass after this one
  // either way, per force-graph's own paint order, so it always lands on
  // top of both regardless of this mode -- irrelevant here since the label
  // sits at the link's midpoint, nowhere near the arrowhead at its end).
  const linkCanvasObjectMode = useCallback(() => 'after', [])

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
  // which the caller (GraphPage) still owns. `assignParallelEdgeCurvature`
  // mutates this copied `links` array in place (adding `curvature`), same
  // reasoning: safe here, never on `edges` itself.
  const graphData = useMemo(() => {
    const links = edges.map((edge) => ({ ...edge }))
    assignParallelEdgeCurvature(links)
    return {
      nodes: nodes.map((node) => ({ ...node })),
      links,
    }
  }, [nodes, edges])

  // Scale the simulation to the circles being drawn, and to the node
  // count -- see `chargeStrengthFor`/`linkDistanceFor`'s own comment for
  // why the latter matters. `collide` is what actually guarantees circles
  // stop landing on top of each other -- charge and link distance only
  // set the *resting* spacing the layout settles toward, and a graph
  // where two nodes overlap hides the edge between them entirely.
  useEffect(() => {
    const engine = graphRef.current
    if (!engine) return
    engine.d3Force('charge').strength(chargeStrengthFor(nodes.length))
    engine.d3Force('link').distance(linkDistanceFor(nodes.length))
    engine.d3Force(
      'collide',
      forceCollide((node) => radiusFor(node) + LABEL_GUTTER),
    )
    engine.d3ReheatSimulation()
    // `width` is a real dependency, not noise: ForceGraph2D is not
    // rendered at all until the container has been measured, so on the
    // first pass there is no engine to configure and this has to run again
    // once there is. `graphData` already changes whenever `nodes`/`edges`
    // do (it's derived from them), so node count changing re-runs this
    // without needing `nodes.length` listed separately.
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

  // Without this, the very first thing a viewer sees is the *unfit*
  // layout: force-graph starts every node clustered near the canvas
  // centre and spreads them out over the simulation's warmup, and
  // `onEngineStop` alone only snaps to the fitted view once all of that
  // settling has already finished -- a visible "spread out, then suddenly
  // fit" transition on every page load, when the page is supposed to open
  // already showing a fitted graph. Re-fitting on every tick keeps the
  // view tracking the layout continuously as it spreads, so it reads as
  // already fit from the very first frame instead of a distinct fit-in
  // transition after the fact. `zoomToFit`'s own transition duration is 0
  // (see `fitToView`), so there's nothing to animate against itself from
  // one tick to the next the way a longer transition would.
  const handleEngineTick = useCallback(() => {
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
    const typeColor = typeColorFor(theme, node.type)

    // Glow pass -- a larger, low-alpha fill of the same circle, colored
    // with this node's own type fill (not one uniform accent), so a
    // Person node glows navy and a Location node glows pale sky: the
    // "depth and hierarchy" this graph's blue identity is built around,
    // not a decorative afterthought. Drawn and fully finished (its own
    // save/restore) before the crisp circle below, which then paints
    // directly over this pass's center -- what's left visible is only the
    // soft halo extending past the crisp circle's true edge.
    ctx.save()
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius * GLOW_RADIUS_MULTIPLIER, 0, 2 * Math.PI)
    ctx.fillStyle = typeColor.fill
    ctx.globalAlpha = GLOW_ALPHA
    ctx.shadowColor = typeColor.fill
    ctx.shadowBlur = GLOW_BLUR
    ctx.fill()
    ctx.restore()

    ctx.save()
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
    // Shadow blur/offset are specified in device space and are *not*
    // affected by the canvas transform, so these stay the literal
    // `0 2px 6px` from DESIGN.md's elevation rule rather than being
    // scaled.
    ctx.shadowColor = palette.glowShadow
    ctx.shadowBlur = 6
    ctx.shadowOffsetY = 2
    ctx.fillStyle = typeColor.fill
    ctx.fill()

    // The boundary that makes a pale fill a distinguishable object at all
    // (WCAG 1.4.11 -- see graphTheme.js's PALETTE.nodeStroke comment).
    // Shadow cleared first so the outline doesn't paint a second copy of
    // it on top of the fill's.
    ctx.shadowColor = 'transparent'
    ctx.shadowBlur = 0
    ctx.shadowOffsetY = 0
    ctx.lineWidth = NODE_STROKE_WIDTH
    ctx.strokeStyle = palette.nodeStroke
    ctx.stroke()
    ctx.restore()

    const fontSize = 10.5
    const nameFontSize = 11
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
    //
    // Given a text *halo* -- `canvasBg`-coloured stroke drawn first, `ink`
    // fill on top -- rather than a flat fill alone: a name sits over
    // whatever the motif's dot-grid, a neighbour's glow, or a curved
    // edge happens to pass beneath it (LABEL_GUTTER keeps a neighbour's
    // *circle* clear, never guaranteed for every line/texture drawn
    // underneath), and the flat `ink` fill alone was reported genuinely
    // hard to read against that. The stroke is the exact `canvasBg`
    // colour, not a generic dark/light halo, so it reads as "this text
    // interrupts the background" the same way `drawLinkLabel`'s pill chip
    // already does for edge labels, rather than a mismatched outline.
    ctx.font = `700 ${nameFontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    const nameY = node.y + radius + 5
    const nameText = truncateToWidth(ctx, node.name, MAX_NODE_DIAMETER * 2)
    ctx.lineJoin = 'round'
    ctx.lineWidth = 3
    ctx.strokeStyle = palette.canvasBg
    ctx.strokeText(nameText, node.x, nameY)
    ctx.fillStyle = palette.ink
    ctx.fillText(nameText, node.x, nameY)
  }

  // Names the relationship on the edge itself -- Story 4.1 shipped
  // directed arrows with no way to tell *what* the connection was short of
  // reading GraphSummary's separate text list. `link.source`/`link.target`
  // are the resolved node objects by the time this runs (`nodeCanvasObject`
  // and `linkCanvasObject` both fire after force-graph's own simulation
  // step has replaced the plain id strings with references, same as
  // `drawNode` above already assumes for `node.x`/`node.y`).
  function drawLinkLabel(link, ctx, globalScale) {
    const start = link.source
    const end = link.target
    if (!start || !end || !Number.isFinite(start.x) || !Number.isFinite(end.x)) return
    // Same legibility floor as the node labels (drawNode) -- at a dense
    // graph's fitted-out zoom, an unreadable relationship name is worse
    // than none; GraphSummary always carries every relationship in full,
    // real text regardless of what the canvas can currently show.
    if (LINK_LABEL_FONT_SIZE * globalScale < MIN_LEGIBLE_FONT_PX) return

    const { x, y } = quadraticMidpoint(start, end, link.curvature ?? 0)
    const label = relationshipLabelFor(link.type)

    ctx.font = `600 ${LINK_LABEL_FONT_SIZE}px sans-serif`
    const textWidth = ctx.measureText(label).width
    const boxWidth = textWidth + LINK_LABEL_PADDING_X * 2
    const boxHeight = LINK_LABEL_FONT_SIZE + LINK_LABEL_PADDING_Y * 2

    ctx.save()
    // Filled with the canvas's own background, not the chrome's translucent
    // `chipBg` -- a translucent fill composited over a line the label chip
    // is meant to interrupt would need its own contrast re-derivation per
    // link color underneath it, which the *exact* canvas colour sidesteps
    // entirely: it just erases whatever was there. Reads as the edge line
    // being interrupted for the label rather than a new shape stacked on
    // it, and both the outline and the text below reuse `nodeStroke` --
    // already proven >=4.5:1 against this exact fill in both themes (see
    // graphTheme.js's PALETTE comment) -- rather than a new pair of
    // colours that would need their own contrast check.
    pillPath(ctx, x, y, boxWidth, boxHeight)
    ctx.fillStyle = palette.canvasBg
    ctx.fill()
    ctx.lineWidth = 1
    ctx.strokeStyle = palette.nodeStroke
    ctx.stroke()

    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = palette.nodeStroke
    ctx.fillText(label, x, y)
    ctx.restore()
  }

  // Vertical divider between the toolbar's three actions -- a plain `<span>`
  // filled with the same `chipBorder` colour the group's own outline uses,
  // rather than a Tailwind `divide-x` border utility: the group's
  // background/border are already inline-styled off `palette` (a
  // graph-specific token, not one of this app's generic Tailwind colors),
  // so the divider stays in that same system instead of mixing in a
  // generic `border-*` class that would visually clash with it.
  function ToolbarDivider() {
    return <span aria-hidden="true" className="my-1.5 w-px self-stretch" style={{ backgroundColor: palette.chipBorder }} />
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-end">
        {/* One grouped "glass" pill rather than three separate floating
            buttons -- the brief's own complaint about the original design
            ("generic square buttons floating top-right with no visual
            integration"). `chipBg`/`chipBorder` are the same translucent
            blue surface the legend below and GraphSummary's redesigned
            chips use, so this toolbar reads as part of one system rather
            than a distinct control style. */}
        <div
          className="flex items-center rounded-full px-0.5 py-0.5 shadow-sm"
          style={{ backgroundColor: palette.chipBg, border: `1px solid ${palette.chipBorder}` }}
        >
          <button
            type="button"
            onClick={() => stepZoom(1 / ZOOM_STEP)}
            className="rounded-full px-3 py-1.5 text-sm font-semibold"
            style={{ color: palette.ink }}
          >
            <span aria-hidden="true">−</span>
            <span className="sr-only">Zoom out</span>
          </button>
          <ToolbarDivider />
          <button
            type="button"
            onClick={() => stepZoom(ZOOM_STEP)}
            className="rounded-full px-3 py-1.5 text-sm font-semibold"
            style={{ color: palette.ink }}
          >
            <span aria-hidden="true">+</span>
            <span className="sr-only">Zoom in</span>
          </button>
          <ToolbarDivider />
          <button
            type="button"
            onClick={resetView}
            className="rounded-full px-3 py-1.5 text-sm font-semibold"
            style={{ color: palette.accentText }}
          >
            Fit
          </button>
        </div>
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
        // `graph-motif` (index.css) paints the dot-grid + vignette behind
        // the canvas -- a plain CSS background on this frame, not drawn
        // into the force-graph canvas itself (see that class's own
        // comment for why). `ForceGraph2D`'s own `backgroundColor` below
        // is transparent specifically so this shows through it.
        className="graph-motif overflow-hidden rounded-xl"
        style={{
          height: CANVAS_HEIGHT,
          border: `1px solid ${palette.cardBorder}`,
          boxShadow: theme === 'dark' ? '0 12px 32px rgba(0, 0, 0, 0.35)' : '0 12px 32px rgba(19, 35, 64, 0.10)',
        }}
        onWheel={markUserViewChange}
        onPointerMove={handlePointerMove}
      >
        {width > 0 && (
          <ForceGraph2D
            ref={graphRef}
            graphData={graphData}
            width={width}
            height={CANVAS_HEIGHT}
            backgroundColor="transparent"
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
            linkCurvature={linkCurvature}
            linkCanvasObjectMode={linkCanvasObjectMode}
            linkCanvasObject={drawLinkLabel}
            onEngineTick={handleEngineTick}
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
          actually on the canvas, so it stays short. Wrapped in the same
          `chipBg`/`chipBorder` surface the toolbar above uses, so the key
          reads as this card's own chrome rather than bare text floating
          under the canvas. */}
      <ul
        aria-label="Entity type key"
        className="mt-3 flex list-none flex-wrap gap-x-4 gap-y-2 rounded-lg px-3 py-2.5 text-sm"
        style={{ backgroundColor: palette.chipBg, border: `1px solid ${palette.chipBorder}`, color: palette.ink }}
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
                className="inline-flex h-5 w-7 items-center justify-center rounded-full text-[11px] font-bold shadow-sm"
                style={{ backgroundColor: typeColor.fill, color: typeColor.text }}
              >
                {badgeFor(type)}
              </span>
              <span className="sr-only">{badgeFor(type)}</span>{' '}
              <span className="font-medium">{type}</span>
            </li>
          )
        })}
      </ul>
      <GraphSummary nodes={nodes} edges={edges} theme={theme} />
    </div>
  )
}
