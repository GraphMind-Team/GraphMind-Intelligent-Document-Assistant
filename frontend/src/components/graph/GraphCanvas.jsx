import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraphKapsule from 'force-graph'
import fromKapsule from 'react-kapsule'
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
const ForceGraph2D = fromKapsule(ForceGraphKapsule)

// UX-DR11's literal spec.
const CANVAS_HEIGHT = 480
const MIN_NODE_DIAMETER = 52
const MAX_NODE_DIAMETER = 78
const MID_NODE_DIAMETER = 65 // used when every node has the same degree -- no ranking signal to normalize against

// Canvas fillStyle needs a literal color, not a CSS custom property --
// these mirror index.css's `--primary`/`--on-primary`/`--card-bg` token
// values by hand (documentsClient.js's ALLOWED_EXTENSIONS comment notes
// the same kind of intentional hand-mirroring). Not read live via
// `getComputedStyle` because that would race `ThemeProvider`'s own
// `data-theme` attribute effect: React fires effects child-before-parent
// within a commit, so this component's effect would read the *previous*
// theme's attribute value on the very render a theme switch happens.
const PALETTE = {
  light: { primary: '#3861A8', onPrimary: '#FFFFFF', cardBg: '#FFFFFF', text: '#10131A' },
  dark: { primary: '#5B8CFF', onPrimary: '#1E222B', cardBg: '#262B35', text: '#E4E7EC' },
}

// Two-letter badges drawn inside each node -- the non-color signal
// AC6/UX-DR28 requires ("entity type... not carried by node colour
// alone"). The entity's name is drawn separately, beneath the node (see
// drawNode) -- the badge alone isn't a substitute for it. GraphSummary's
// grouped-by-type list is a second, always-visible way to see type.
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

function diameterFor(degree, minDegree, maxDegree) {
  if (minDegree === maxDegree) return MID_NODE_DIAMETER
  const ratio = (degree - minDegree) / (maxDegree - minDegree)
  return MIN_NODE_DIAMETER + ratio * (MAX_NODE_DIAMETER - MIN_NODE_DIAMETER)
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

// Read-only knowledge-graph canvas (Story 4.1, UX-DR11). `react-force-
// graph`'s `ForceGraph2D` lays entities out with its physics engine, but
// every pointer interaction is disabled below -- no click-to-query, no
// drag, no zoom/pan, and (since `enablePointerInteraction` is off) no
// hover reveal either. That's what makes "if nodes carry no interaction
// at all, that is stated explicitly" (AC7) literally true rather than a
// restriction bolted onto an otherwise-interactive canvas -- GraphSummary
// alongside it states this in plain visible text.
//
// Assumes `graph.nodes` is non-empty -- GraphPage.jsx renders its own
// empty-state message instead of this component when there are no
// entities at all.
export default function GraphCanvas({ graph }) {
  const { theme } = useTheme()
  const containerRef = useRef(null)
  const width = useContainerWidth(containerRef)

  const palette = PALETTE[theme] ?? PALETTE.light
  const { nodes, edges } = graph

  const degrees = nodes.map((node) => node.degree)
  const minDegree = degrees.length ? Math.min(...degrees) : 0
  const maxDegree = degrees.length ? Math.max(...degrees) : 0

  // `force-graph` mutates the objects it's given (adds `x`/`y`/`vx`/
  // `vy` for the simulation) -- copied here so it never mutates `graph`
  // itself, which the caller (GraphPage) still owns.
  const graphData = useMemo(
    () => ({
      nodes: nodes.map((node) => ({ ...node })),
      links: edges.map((edge) => ({ ...edge })),
    }),
    [nodes, edges],
  )

  function drawNode(node, ctx, globalScale) {
    // `ctx` is already in zoom/pan space -- dividing by `globalScale`
    // keeps the diameter/font spec true in actual on-screen pixels
    // regardless of the force layout's auto-fit zoom (force-graph's own
    // documented idiom for constant-screen-size drawing).
    const diameter = diameterFor(node.degree, minDegree, maxDegree)
    const radius = diameter / 2 / globalScale

    ctx.save()
    ctx.beginPath()
    ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
    ctx.shadowColor = 'rgba(10, 46, 99, 0.25)'
    ctx.shadowBlur = 6 / globalScale
    ctx.shadowOffsetY = 2 / globalScale
    ctx.fillStyle = palette.primary
    ctx.fill()
    ctx.restore()

    const fontSize = 10.5 / globalScale
    ctx.font = `700 ${fontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = palette.onPrimary
    ctx.fillText(badgeFor(node.type), node.x, node.y)

    // Entity name, drawn beneath the node rather than inside it -- the
    // circle is too small at MIN_NODE_DIAMETER to fit both the type badge
    // and a full name legibly. Same /globalScale treatment as the badge
    // and radius above, so it stays a constant on-screen size regardless
    // of the force layout's auto-fit zoom.
    const nameFontSize = 10 / globalScale
    ctx.font = `500 ${nameFontSize}px sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = palette.text
    ctx.fillText(node.name, node.x, node.y + radius + 4 / globalScale)
  }

  return (
    <div>
      <div
        ref={containerRef}
        role="img"
        aria-label={`Knowledge graph: ${nodes.length} ${nodes.length === 1 ? 'entity' : 'entities'}, ${edges.length} ${edges.length === 1 ? 'relationship' : 'relationships'}. Read-only — hover and click are disabled.`}
        className="overflow-hidden rounded-xl border border-border bg-card-bg"
        style={{ height: CANVAS_HEIGHT }}
      >
        {width > 0 && (
          <ForceGraph2D
            graphData={graphData}
            width={width}
            height={CANVAS_HEIGHT}
            backgroundColor={palette.cardBg}
            nodeCanvasObject={drawNode}
            nodeLabel={null}
            enableNodeDrag={false}
            enablePointerInteraction={false}
            enableZoomInteraction={false}
            enablePanInteraction={false}
          />
        )}
      </div>
      <GraphSummary nodes={nodes} edges={edges} />
    </div>
  )
}
