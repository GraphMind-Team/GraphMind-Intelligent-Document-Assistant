import { render, screen } from '@testing-library/react'
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

const GRAPH = {
  nodes: [
    { id: 'Person:Maria', name: 'Maria', type: 'Person', degree: 3 },
    { id: 'Organization:TechCorp', name: 'TechCorp', type: 'Organization', degree: 1 },
  ],
  edges: [{ source: 'Person:Maria', target: 'Organization:TechCorp', type: 'WORKS_AT' }],
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

  it('renders the wrapper with a read-only aria-label naming the entity/relationship counts', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const wrapper = screen.getByRole('img')
    expect(wrapper).toHaveAccessibleName(/2 entities, 1 relationship/i)
    expect(wrapper).toHaveAccessibleName(/read-only/i)
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

  it('draws a node without throwing, with the type badge and the entity name as labels (AC1/AC6)', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    const ctx = {
      save: vi.fn(),
      restore: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillText: vi.fn(),
    }

    expect(() =>
      props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Person', name: 'Maria' }, ctx, 1),
    ).not.toThrow()
    expect(ctx.arc).toHaveBeenCalled()
    expect(ctx.fillText).toHaveBeenCalledWith('PE', 0, 0)
    expect(ctx.fillText).toHaveBeenCalledWith('Maria', 0, expect.any(Number))
  })

  it('fills each entity type with its own colour, redundantly with the badge', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    // Captured at fill() time, not read back afterwards: the label draws
    // last and would otherwise overwrite fillStyle with the text colour.
    const fillFor = (node) => {
      let circleFill
      const ctx = {
        save: vi.fn(),
        restore: vi.fn(),
        beginPath: vi.fn(),
        arc: vi.fn(),
        fill: vi.fn(() => {
          circleFill = ctx.fillStyle
        }),
        fillText: vi.fn(),
      }
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
    const ctx = {
      save: vi.fn(),
      restore: vi.fn(),
      beginPath: vi.fn(),
      arc: vi.fn(),
      fill: vi.fn(),
      fillText: vi.fn(),
    }

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
      const ctx = {
        save: vi.fn(),
        restore: vi.fn(),
        beginPath: vi.fn(),
        arc: vi.fn(),
        fill: vi.fn(),
        fillText: vi.fn(),
      }
      props.nodeCanvasObject({ x: 0, y: 0, degree: 3, type: 'Person', name: 'Maria' }, ctx, globalScale)
      return ctx.arc.mock.calls[0][2]
    }

    // Same world-space radius at every zoom -- the on-screen size then
    // follows the transform, instead of being cancelled out by it.
    expect(radiusAt(1)).toBe(radiusAt(0.3))
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

  it('gives links a visible theme colour and a direction arrow', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.linkDirectionalArrowLength).toBeGreaterThan(0)
    expect(props.linkColor()).toBe('rgba(69, 78, 96, 0.45)')
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
