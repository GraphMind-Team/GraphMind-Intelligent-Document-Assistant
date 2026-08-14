import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GraphPage from './GraphPage'
import { useAuth } from '../context/AuthContext'
import * as graphClient from '../api/graphClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
// GraphCanvas pulls in react-force-graph and ThemeContext -- its own
// rendering/interaction behavior is covered by GraphCanvas.test.jsx.
// GraphPage's job is fetch/loading/error/empty-state orchestration, so
// GraphCanvas is stubbed to a marker that just proves the right graph
// data reached it.
vi.mock('../components/graph/GraphCanvas', () => ({
  default: ({ graph }) => <div data-testid="graph-canvas-stub">{graph.nodes.length} nodes</div>,
}))

afterEach(() => {
  vi.restoreAllMocks()
})

describe('GraphPage', () => {
  it('shows a loading state, then the canvas once entities are fetched', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(graphClient, 'getGraph').mockResolvedValue({
      nodes: [{ id: 'Person:A', name: 'A', type: 'Person', degree: 1 }],
      edges: [],
      total_node_count: 1,
    })

    render(<GraphPage />)

    expect(screen.getByText(/loading graph/i)).toBeInTheDocument()
    expect(await screen.findByTestId('graph-canvas-stub')).toHaveTextContent('1 nodes')
  })

  it('shows a plain-language empty state instead of the canvas when there are no entities (AC8)', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(graphClient, 'getGraph').mockResolvedValue({ nodes: [], edges: [], total_node_count: 0 })

    render(<GraphPage />)

    expect(await screen.findByText(/No graph yet\./)).toBeInTheDocument()
    expect(screen.queryByTestId('graph-canvas-stub')).not.toBeInTheDocument()
  })

  it('shows the fetch error instead of the canvas when the request fails', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(graphClient, 'getGraph').mockRejectedValue(new Error('Not authenticated.'))

    render(<GraphPage />)

    expect(await screen.findByRole('alert')).toHaveTextContent('Not authenticated.')
    expect(screen.queryByTestId('graph-canvas-stub')).not.toBeInTheDocument()
  })

  it('shows the "showing top N of M" note when the graph was capped', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(graphClient, 'getGraph').mockResolvedValue({
      nodes: [{ id: 'Person:A', name: 'A', type: 'Person', degree: 1 }],
      edges: [],
      total_node_count: 3241,
    })

    render(<GraphPage />)

    expect(
      await screen.findByText(/Showing the 1 most-connected entities of 3241 total/),
    ).toBeInTheDocument()
    expect(screen.getByText(/connections to entities outside this view aren't drawn/i)).toBeInTheDocument()
  })

  it('does not show the capped note when every entity fit', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(graphClient, 'getGraph').mockResolvedValue({
      nodes: [{ id: 'Person:A', name: 'A', type: 'Person', degree: 1 }],
      edges: [],
      total_node_count: 1,
    })

    render(<GraphPage />)

    await screen.findByTestId('graph-canvas-stub')
    expect(screen.queryByText(/most-connected entities of/)).not.toBeInTheDocument()
  })
})
