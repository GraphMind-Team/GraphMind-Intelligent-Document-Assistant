import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// `force-graph` needs a real canvas 2D context and cannot render under
// jsdom -- mocked entirely (both the vanilla engine and the
// `react-kapsule` wrapper GraphCanvas.jsx builds `ForceGraph2D` from), so
// only wrapper markup/props and the `nodeCanvasObject` callback (invoked
// directly below) are exercised here. GraphSummary.test.jsx covers the
// real, RTL-testable accessible content this component renders alongside
// the canvas.
const MockForceGraph2D = vi.fn(() => <div data-testid="force-graph-stub" />)
// The engine's imperative zoom API, which GraphCanvas reaches through the
// forwarded ref -- `zoom` doubles as getter (no args) and setter, exactly
// as force-graph's own kapsule accessor does.
const MEASURED_BBOX = { x: [-100, 100], y: [-80, 80] }
const mockChargeForce = { strength: vi.fn() }
const mockLinkForce = { distance: vi.fn() }
const mockEngine = {
  zoomToFit: vi.fn(),
  zoom: vi.fn(() => 1),
  getGraphBbox: vi.fn(() => MEASURED_BBOX),
  d3Force: vi.fn((name) => (name === 'charge' ? mockChargeForce : mockLinkForce)),
  d3ReheatSimulation: vi.fn(),
}
vi.mock('force-graph', () => ({ default: () => ({}) }))
vi.mock('react-kapsule', async () => {
  const { forwardRef, useImperativeHandle } = await import('react')
  return {
    default: () =>
      forwardRef((props, ref) => {
        useImperativeHandle(ref, () => mockEngine, [])
        return MockForceGraph2D(props)
      }),
  }
})
vi.mock('../../context/ThemeContext', () => ({ useTheme: () => ({ theme: 'light' }) }))

import GraphCanvas from './GraphCanvas'

// A stand-in 2D context for directly invoking `nodeCanvasObject`.
// `measureText` returns a width proportional to string length -- rough,
// but enough for `truncateToWidth`'s binary-search-by-width logic to
// exercise real shortening instead of throwing on a missing method.
function makeCtx(overrides = {}) {
  return {
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    closePath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillText: vi.fn(),
    strokeText: vi.fn(),
    measureText: vi.fn((text) => ({ width: text.length * 6 })),
    ...overrides,
  }
}

const GRAPH = {
  nodes: [
    { id: 'Person:Maria', name: 'Maria', type: 'Person', degree: 3 },
    { id: 'Organization:TechCorp', name: 'TechCorp', type: 'Organization', degree: 1 },
  ],
  edges: [{ source: 'Person:Maria', target: 'Organization:TechCorp', type: 'WORKS_AT' }],
  total_node_count: 2,
}

// Two distinct relationship types between the exact same pair -- a real
// shape under OD-1's closed vocabulary (see `assignParallelEdgeCurvature`'s
// own comment), not a data error this fixture is inventing.
const PARALLEL_EDGES_GRAPH = {
  nodes: [
    { id: 'Person:Maria', name: 'Maria', type: 'Person', degree: 2 },
    { id: 'Organization:TechCorp', name: 'TechCorp', type: 'Organization', degree: 2 },
  ],
  edges: [
    { source: 'Person:Maria', target: 'Organization:TechCorp', type: 'WORKS_AT' },
    { source: 'Person:Maria', target: 'Organization:TechCorp', type: 'RELATED_TO' },
  ],
  total_node_count: 2,
}

describe('GraphCanvas', () => {
  beforeEach(() => {
    MockForceGraph2D.mockClear()
    mockEngine.zoomToFit.mockClear()
    mockEngine.zoom.mockClear()
    mockEngine.zoom.mockImplementation(() => 1)
    mockEngine.getGraphBbox.mockClear()
    mockEngine.getGraphBbox.mockImplementation(() => MEASURED_BBOX)
    mockEngine.d3Force.mockClear()
    mockEngine.d3ReheatSimulation.mockClear()
    mockChargeForce.strength.mockClear()
    mockLinkForce.distance.mockClear()
    // jsdom reports 0 for every element's clientWidth (no real layout) --
    // the component gates rendering ForceGraph2D on a positive measured
    // width, so this stub value is what lets that gate open in tests.
    Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
      configurable: true,
      value: 600,
    })
  })

  afterEach(() => {
    delete HTMLElement.prototype.clientWidth
  })

  it('gives the canvas a short accessible name, leaving the full read-only/count statement to GraphSummary', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    // Kept brief on purpose: GraphSummary's visible text is the real
    // accessible content and states the counts and read-only nature
    // itself, right below this element -- duplicating that whole sentence
    // into the aria-label would have a screen reader announce it twice.
    const wrapper = screen.getByRole('img')
    expect(wrapper).toHaveAccessibleName(/knowledge graph/i)
    expect(wrapper).not.toHaveAccessibleName(/2 entities, 1 relationship/i)
  })

  it('passes graphData built from the given nodes/edges to ForceGraph2D', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.graphData.nodes).toHaveLength(2)
    expect(props.graphData.links).toEqual([
      { source: 'Person:Maria', target: 'Organization:TechCorp', type: 'WORKS_AT' },
    ])
  })

  it('leaves the graph itself read-only while allowing the viewport to move (AC5/AC7)', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    // No click-to-query, no drag-to-rearrange, no hover reveal.
    expect(props.enableNodeDrag).toBe(false)
    expect(props.enablePointerInteraction).toBe(false)
    // Moving the viewport is not editing the graph, and a fitted 150-node
    // view is unreadable without it.
    expect(props.enableZoomInteraction).toBe(true)
    expect(props.enablePanInteraction).toBe(true)
  })

  it('zooms in and out by a step, bounded, when the buttons are pressed', async () => {
    const user = userEvent.setup()
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    mockEngine.zoom.mockClear()
    mockEngine.zoom.mockImplementation(() => 1)
    await user.click(screen.getByRole('button', { name: /zoom in/i }))
    const zoomedIn = mockEngine.zoom.mock.calls.at(-1)[0]
    expect(zoomedIn).toBeGreaterThan(1)

    mockEngine.zoom.mockImplementation(() => 1)
    await user.click(screen.getByRole('button', { name: /zoom out/i }))
    const zoomedOut = mockEngine.zoom.mock.calls.at(-1)[0]
    expect(zoomedOut).toBeLessThan(1)

    // Never past the bounds the engine itself is configured with.
    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(zoomedIn).toBeLessThanOrEqual(props.maxZoom)
    expect(zoomedOut).toBeGreaterThanOrEqual(props.minZoom)
  })

  it('stops auto-fitting once the user has zoomed, until Fit is pressed', async () => {
    const user = userEvent.setup()
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    await user.click(screen.getByRole('button', { name: /zoom in/i }))

    // The layout settling must not now yank the view back.
    mockEngine.zoomToFit.mockClear()
    MockForceGraph2D.mock.calls.at(-1)[0].onEngineStop()
    expect(mockEngine.zoomToFit).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /fit/i }))
    expect(mockEngine.zoomToFit).toHaveBeenCalled()
  })

  it('stops auto-fitting once the user has panned, the same as zooming', async () => {
    const user = userEvent.setup()
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    // A drag: pointer moving with a button held. Panning is force-graph's
    // own (`enablePanInteraction`); this only has to notice it happened.
    fireEvent.pointerMove(screen.getByRole('img'), { buttons: 1 })

    mockEngine.zoomToFit.mockClear()
    MockForceGraph2D.mock.calls.at(-1)[0].onEngineStop()
    expect(mockEngine.zoomToFit).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /fit/i }))
    expect(mockEngine.zoomToFit).toHaveBeenCalled()
  })

  it('keeps auto-fitting after a pointer merely crosses the canvas', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    // No button held -- not a pan, so it must not count as the user
    // taking over the viewport.
    fireEvent.pointerMove(screen.getByRole('img'), { buttons: 0 })

    mockEngine.zoomToFit.mockClear()
    MockForceGraph2D.mock.calls.at(-1)[0].onEngineStop()
    expect(mockEngine.zoomToFit).toHaveBeenCalled()
  })

  it('does not treat force-graph’s own zoom events as a user gesture', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    // force-graph calls `zoom.scaleTo` itself on every data change (its
    // ZOOM2NODES_FACTOR / cbrt(N) heuristic) and d3-zoom fires the same
    // event for that as for a real gesture. Wiring `onZoom` would
    // therefore latch "the user moved the view" on mount and auto-fit
    // would never run again -- the input events are listened to instead.
    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.onZoom).toBeUndefined()

    props.onEngineStop()
    expect(mockEngine.zoomToFit).toHaveBeenCalled()
  })

  it('outlines every node so a pale fill is still a distinguishable shape (WCAG 1.4.11)', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    let strokeAtOutlineTime
    let shadowAtOutlineTime
    const ctx = makeCtx({
      stroke: vi.fn(() => {
        strokeAtOutlineTime = ctx.strokeStyle
        shadowAtOutlineTime = ctx.shadowBlur
      }),
    })

    // The palest light-mode fill (#B7D3F6, 1.43:1 on the graph canvas bg)
    // -- the one the outline exists for.
    props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Location', name: 'Sofia' }, ctx, 1)

    expect(ctx.stroke).toHaveBeenCalled()
    // graphTheme.js's `ink`, 14.56:1 against the light graph canvas bg.
    expect(strokeAtOutlineTime).toBe('#132340')
    // Cleared first, so the outline doesn't repaint the fill's shadow.
    expect(shadowAtOutlineTime).toBe(0)
  })

  it('draws a node without throwing, with the type badge and the entity name as labels (AC1/AC6)', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()

    expect(() =>
      props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Person', name: 'Maria' }, ctx, 1),
    ).not.toThrow()
    expect(ctx.arc).toHaveBeenCalled()
    expect(ctx.fillText).toHaveBeenCalledWith('PE', 0, 0)
    expect(ctx.fillText).toHaveBeenCalledWith('Maria', 0, expect.any(Number))
  })

  it('truncates a name that would run wider than roughly two node-widths, with an ellipsis', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()
    const longName = 'Northbridge Logistics International Holdings Group'

    props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Organization', name: longName }, ctx, 1)

    const nameCall = ctx.fillText.mock.calls.find(([text]) => text !== 'OR')
    expect(nameCall[0]).not.toBe(longName)
    expect(nameCall[0]).toMatch(/…$/)
    expect(nameCall[0].length).toBeLessThan(longName.length)
  })

  it('draws a short name in full, with no ellipsis', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()

    props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Organization', name: 'Acme' }, ctx, 1)

    expect(ctx.fillText).toHaveBeenCalledWith('Acme', 0, expect.any(Number))
  })

  it('fills each entity type with its own colour, redundantly with the badge', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    // Captured at fill() time, not read back afterwards: the label draws
    // last and would otherwise overwrite fillStyle with the text colour.
    const fillFor = (node) => {
      let circleFill
      const ctx = makeCtx({
        fill: vi.fn(() => {
          circleFill = ctx.fillStyle
        }),
      })
      props.nodeCanvasObject({ x: 0, y: 0, degree: 3, ...node }, ctx, 1)
      return circleFill
    }

    const person = fillFor({ type: 'Person', name: 'Maria' })
    const organization = fillFor({ type: 'Organization', name: 'TechCorp' })
    expect(person).not.toBe(organization)

    // An unknown type must still draw rather than blow up on an undefined
    // fill.
    expect(() => fillFor({ type: 'Spaceship', name: 'Serenity' })).not.toThrow()
  })

  it('omits both labels when the fitted zoom would render them illegibly small', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()

    // 10 * 0.3 = 3px on screen -- the circle still carries shape and
    // connectivity, GraphSummary carries the names.
    props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Person', name: 'Maria' }, ctx, 0.3)

    expect(ctx.arc).toHaveBeenCalled()
    expect(ctx.fillText).not.toHaveBeenCalled()
  })

  it('draws nodes in world units so a zoomed-out fit actually shrinks them', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const radiusAt = (globalScale) => {
      const ctx = makeCtx()
      props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Person', name: 'Maria' }, ctx, globalScale)
      return ctx.arc.mock.calls[0][2]
    }

    // Same world-space radius at every zoom -- the on-screen size then
    // follows the transform, instead of being cancelled out by it.
    expect(radiusAt(1)).toBe(radiusAt(0.3))
  })

  it('keeps re-fitting on every simulation tick, not just once the layout settles', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    mockEngine.zoomToFit.mockClear()

    // Without this, the first thing a viewer sees is force-graph's own
    // unfit initial layout (nodes clustered near centre, spreading out
    // over the warmup) with the fit only snapping in once it settles --
    // `onEngineTick` fires on every step of that settling, not only the
    // last one.
    props.onEngineTick()
    props.onEngineTick()

    expect(mockEngine.zoomToFit).toHaveBeenCalledTimes(2)
  })

  it('stops auto-fitting on tick once the user has zoomed or panned deliberately', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    mockEngine.zoomToFit.mockClear()

    // A wheel event on the canvas frame is force-graph's own zoom
    // gesture (`markUserViewChange`, wired to the container's `onWheel`) --
    // the same signal `stepZoom` and the existing pan-drag test already
    // use to mark a deliberate user gesture.
    fireEvent.wheel(screen.getByLabelText('Knowledge graph visualization'))

    props.onEngineTick()

    expect(mockEngine.zoomToFit).not.toHaveBeenCalled()
  })

  it('fits the graph into the canvas once the layout settles, without magnifying past the spec size', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    mockEngine.zoomToFit.mockClear()
    mockEngine.zoom.mockClear()
    // A graph small enough that fitting it would zoom *in*.
    mockEngine.zoom.mockImplementation(() => 2.4)

    props.onEngineStop()

    expect(mockEngine.zoomToFit).toHaveBeenCalled()
    expect(mockEngine.zoom).toHaveBeenLastCalledWith(1)
  })

  it('leaves a zoomed-out fit alone, so a large graph stays fully visible', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    mockEngine.zoom.mockClear()
    mockEngine.zoom.mockImplementation(() => 0.31)

    props.onEngineStop()

    // Read once to check the clamp, never written back.
    expect(mockEngine.zoom).toHaveBeenCalledTimes(1)
    expect(mockEngine.zoom).toHaveBeenCalledWith()
  })

  it('does not fit before the simulation has placed anything', async () => {
    // d3-zoom's scaleTo is relative to the current transform, so a single
    // fit against an unmeasured (NaN) bounding box would poison it
    // permanently and blank the canvas -- including for every later,
    // well-measured fit.
    mockEngine.getGraphBbox.mockImplementation(() => ({ x: [NaN, NaN], y: [NaN, NaN] }))

    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    expect(mockEngine.getGraphBbox).toHaveBeenCalled()
    expect(mockEngine.zoomToFit).not.toHaveBeenCalled()
    expect(mockEngine.zoom).not.toHaveBeenCalled()
  })

  it('scales the simulation to the painted node size instead of the default dot', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    // At the d3 defaults these 52-78px circles land inside each other and
    // bury their own edges -- collide is what prevents that.
    const collide = mockEngine.d3Force.mock.calls.find(([name]) => name === 'collide')
    expect(collide).toBeDefined()
    expect(collide[1]).toBeDefined()
    expect(mockChargeForce.strength).toHaveBeenCalled()
    expect(mockLinkForce.distance).toHaveBeenCalled()
    expect(mockEngine.d3ReheatSimulation).toHaveBeenCalled()

    // The engine's own size math (bounding box for the fit, arrow
    // placement) has to agree with what drawNode paints.
    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.nodeRelSize).toBe(1)
    expect(Math.sqrt(props.nodeVal({ degree: 3 })) * props.nodeRelSize).toBeGreaterThan(20)
  })

  it('pushes nodes apart harder as the graph grows, so a many-entity account does not collapse into a dense tangle', async () => {
    // A real 8-entity account graph was reported crowding into an
    // overlapping clump even with `collide` in place -- `collide` alone
    // only stops circles landing exactly on top of each other, not the
    // layout as a whole from crowding. Charge/link-distance must scale
    // with node count, not stay fixed, for this to actually resolve as
    // accounts grow rather than only at the exact size this was tuned
    // against.
    const bigGraph = {
      nodes: Array.from({ length: 20 }, (_, i) => ({
        id: `Person:P${i}`,
        name: `Person ${i}`,
        type: 'Person',
        degree: 1,
      })),
      edges: [],
      total_node_count: 20,
    }

    const { unmount } = render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')
    const smallGraphCharge = mockChargeForce.strength.mock.calls.at(-1)[0]
    const smallGraphLinkDistance = mockLinkForce.distance.mock.calls.at(-1)[0]
    unmount()

    mockChargeForce.strength.mockClear()
    mockLinkForce.distance.mockClear()
    render(<GraphCanvas graph={bigGraph} />)
    await screen.findByTestId('force-graph-stub')
    const bigGraphCharge = mockChargeForce.strength.mock.calls.at(-1)[0]
    const bigGraphLinkDistance = mockLinkForce.distance.mock.calls.at(-1)[0]

    // Charge is negative (repulsive) -- "stronger" means more negative.
    expect(bigGraphCharge).toBeLessThan(smallGraphCharge)
    expect(bigGraphLinkDistance).toBeGreaterThan(smallGraphLinkDistance)
  })

  it('gives links a visible theme colour and a direction arrow', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.linkDirectionalArrowLength).toBeGreaterThan(0)
    // 3.67:1 against the light graph canvas bg -- an edge is the
    // relationship this view exists to show, so WCAG 1.4.11's 3:1 applies
    // to it (see graphTheme.js's PALETTE comment for the derivation).
    expect(props.linkColor()).toBe('rgba(34, 80, 143, 0.7)')
  })

  it('draws the relationship label after the line, in plain language rather than the raw enum value', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.linkCanvasObjectMode()).toBe('after')

    const ctx = makeCtx()
    const link = { source: { x: 0, y: 0 }, target: { x: 100, y: 0 }, type: 'WORKS_AT' }
    props.linkCanvasObject(link, ctx, 1)

    expect(ctx.fillText).toHaveBeenCalledWith('Works at', 50, 0)
  })

  it('title-cases an unrecognized relationship type rather than drawing the raw enum value', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()
    const link = { source: { x: 0, y: 0 }, target: { x: 100, y: 0 }, type: 'SOME_NEW_TYPE' }
    props.linkCanvasObject(link, ctx, 1)

    expect(ctx.fillText).toHaveBeenCalledWith('Some new type', 50, 0)
  })

  it('omits the relationship label when the fitted zoom would render it illegibly small', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()
    const link = { source: { x: 0, y: 0 }, target: { x: 100, y: 0 }, type: 'WORKS_AT' }
    props.linkCanvasObject(link, ctx, 0.3)

    expect(ctx.fillText).not.toHaveBeenCalled()
  })

  it('positions a curved relationship label on the curve itself, not the straight chord between the two nodes', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = makeCtx()
    const link = { source: { x: 0, y: 0 }, target: { x: 100, y: 0 }, type: 'WORKS_AT', curvature: 0.2 }
    props.linkCanvasObject(link, ctx, 1)

    const call = ctx.fillText.mock.calls.find(([text]) => text === 'Works at')
    // The straight-chord midpoint would land at y=0 -- a nonzero curvature
    // must move the label off of it.
    expect(call[2]).not.toBe(0)
  })

  it('curves two relationships between the same pair of entities apart, so their labels do not land on top of each other', async () => {
    render(<GraphCanvas graph={PARALLEL_EDGES_GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const [first, second] = props.graphData.links
    expect(first.curvature).not.toBe(0)
    expect(first.curvature).toBeCloseTo(-second.curvature)
  })

  it('leaves a single relationship between a pair as a straight line', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.linkCurvature(props.graphData.links[0])).toBe(0)
  })

  it('spells out each two-letter type badge in a legend, for the types on the canvas', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const legend = screen.getByRole('list', { name: /entity type key/i })
    expect(legend).toHaveTextContent(/PE\s+Person/)
    expect(legend).toHaveTextContent(/OR\s+Organization/)
    // Only types actually present -- no dictionary dump.
    expect(legend).not.toHaveTextContent(/Location/)
  })

  it('renders GraphSummary alongside the canvas', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    expect(screen.getByText('View as list')).toBeInTheDocument()
  })
})
