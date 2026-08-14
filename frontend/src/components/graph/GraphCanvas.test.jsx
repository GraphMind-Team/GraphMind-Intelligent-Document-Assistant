import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// `force-graph` needs a real canvas 2D context and cannot render under
// jsdom -- mocked entirely (both the vanilla engine and the
// `react-kapsule` wrapper GraphCanvas.jsx builds `ForceGraph2D` from), so
// only wrapper markup/props and the `nodeCanvasObject` callback (invoked
// directly below) are exercised here. GraphSummary.test.jsx covers the
// real, RTL-testable accessible content this component renders alongside
// the canvas.
const MockForceGraph2D = vi.fn(() => <div data-testid="force-graph-stub" />)
vi.mock('force-graph', () => ({ default: () => ({}) }))
vi.mock('react-kapsule', () => ({
  default: () => (props) => MockForceGraph2D(props),
}))
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

  it('disables every pointer/drag/zoom interaction (AC5/AC7)', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    const props = MockForceGraph2D.mock.calls.at(-1)[0]
    expect(props.enableNodeDrag).toBe(false)
    expect(props.enablePointerInteraction).toBe(false)
    expect(props.enableZoomInteraction).toBe(false)
    expect(props.enablePanInteraction).toBe(false)
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

  it('renders GraphSummary alongside the canvas', async () => {
    render(<GraphCanvas graph={GRAPH} />)
    await screen.findByTestId('force-graph-stub')

    expect(screen.getByText('View as list')).toBeInTheDocument()
  })
})
