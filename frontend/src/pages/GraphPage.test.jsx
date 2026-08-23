import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import GraphPage from './GraphPage'
import { useAuth } from '../context/AuthContext'
import * as graphClient from '../api/graphClient'
import * as documentsClient from '../api/documentsClient'
import * as foldersClient from '../api/foldersClient'

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

  describe('document scope panel', () => {
    const DOCS = [
      { id: 'doc-1', filename: 'Team_Directory.md', folder_id: null },
      { id: 'doc-2', filename: 'Vendor.pdf', folder_id: null },
    ]

    function mockScopePanelData() {
      vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue(DOCS)
      vi.spyOn(foldersClient, 'listFolders').mockResolvedValue([])
    }

    it('forwards the selected document id to getGraph and re-renders with the narrowed result', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      mockScopePanelData()
      const getGraphSpy = vi
        .spyOn(graphClient, 'getGraph')
        .mockResolvedValueOnce({
          nodes: [
            { id: 'Person:A', name: 'A', type: 'Person', degree: 1 },
            { id: 'Person:B', name: 'B', type: 'Person', degree: 1 },
          ],
          edges: [],
          total_node_count: 2,
        })
        .mockResolvedValueOnce({
          nodes: [{ id: 'Person:A', name: 'A', type: 'Person', degree: 0 }],
          edges: [],
          total_node_count: 1,
        })
      const user = userEvent.setup()

      render(<GraphPage />)
      await screen.findByTestId('graph-canvas-stub')

      await user.click(screen.getByRole('button', { name: 'Choose document' }))
      const checkbox = await screen.findByLabelText('Team_Directory.md')
      await user.click(checkbox)

      await waitFor(() => expect(getGraphSpy).toHaveBeenLastCalledWith(expect.anything(), ['doc-1']))
      expect(await screen.findByTestId('graph-canvas-stub')).toHaveTextContent('1 nodes')
    })

    it('"Select all" triggers exactly one additional fetch, not one per document', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      mockScopePanelData()
      const getGraphSpy = vi.spyOn(graphClient, 'getGraph').mockResolvedValue({
        nodes: [],
        edges: [],
        total_node_count: 0,
      })
      const user = userEvent.setup()

      render(<GraphPage />)
      await waitFor(() => expect(getGraphSpy).toHaveBeenCalledTimes(1))

      await user.click(screen.getByRole('button', { name: 'Choose document' }))
      await screen.findByText('Team_Directory.md')
      await user.click(screen.getByRole('button', { name: 'Select all' }))

      await waitFor(() => expect(getGraphSpy).toHaveBeenLastCalledWith(expect.anything(), ['doc-1', 'doc-2']))
      // Exactly one more call for the whole "Select all" action -- not one
      // per document it selected.
      expect(getGraphSpy).toHaveBeenCalledTimes(2)
    })

    it('a stale response from a superseded selection never overwrites a later selection\'s result', async () => {
      useAuth.mockReturnValue({ authFetch: vi.fn() })
      mockScopePanelData()

      let resolveFirst
      let resolveSecond
      const firstFetch = new Promise((resolve) => {
        resolveFirst = resolve
      })
      const secondFetch = new Promise((resolve) => {
        resolveSecond = resolve
      })
      vi.spyOn(graphClient, 'getGraph').mockImplementationOnce(() => firstFetch).mockImplementationOnce(() => secondFetch)
      const user = userEvent.setup()

      render(<GraphPage />)
      await screen.findByRole('button', { name: 'Choose document' }) // page rendered, first fetch in flight

      await user.click(screen.getByRole('button', { name: 'Choose document' }))
      const checkbox = await screen.findByLabelText('Team_Directory.md')
      await user.click(checkbox) // triggers the second fetch while the first is still pending

      // The second (later) selection's response lands first...
      resolveSecond({ nodes: [{ id: 'Person:B', name: 'B', type: 'Person', degree: 0 }], edges: [], total_node_count: 1 })
      await screen.findByTestId('graph-canvas-stub')
      // ...then the first (now-superseded) response arrives late. It must
      // not stomp the already-rendered, more current result.
      resolveFirst({
        nodes: [
          { id: 'Person:A', name: 'A', type: 'Person', degree: 1 },
          { id: 'Person:B', name: 'B', type: 'Person', degree: 1 },
        ],
        edges: [],
        total_node_count: 2,
      })

      await waitFor(() => expect(screen.getByTestId('graph-canvas-stub')).toHaveTextContent('1 nodes'))
      // Give any errant late state update a chance to land before asserting
      // it didn't.
      await new Promise((resolve) => setTimeout(resolve, 10))
      expect(screen.getByTestId('graph-canvas-stub')).toHaveTextContent('1 nodes')
    })
  })
})
