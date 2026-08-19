import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { getGraph } from '../api/graphClient'
import GraphCanvas from '../components/graph/GraphCanvas'

// Graph Preview (Story 4.1), replacing the Story 1.5 placeholder. A pure
// read: fetch -> loading/error/empty-state -> render, mirroring
// DocumentsPage.jsx's fetch pattern.
export default function GraphPage() {
  const { authFetch } = useAuth()
  const [graph, setGraph] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchGraph = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getGraph(authFetch)
      setGraph(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    fetchGraph()
  }, [fetchGraph])

  const hasEntities = Boolean(graph && graph.nodes.length > 0)
  // Story 4.1's node cap (`GRAPH_NODE_LIMIT` in neo4j_client.py): the
  // backend can return fewer entities than the account actually has.
  const isCapped = Boolean(graph && graph.total_node_count > graph.nodes.length)

  return (
    // One cohesive card -- header, controls, canvas, legend and the "View
    // as list" fallback all inside the same `--graph-card-*` surface
    // GraphCanvas.jsx's own inner canvas frame and GraphSummary.jsx's
    // chips already draw from, rather than the header sitting on the
    // page's plain background above an unrelated-looking canvas box.
    // Referenced via `var()` in an arbitrary Tailwind value, not a
    // `useTheme()` read: unlike GraphCanvas (whose canvas fills need a
    // literal JS color), this is plain CSS, and the `--graph-*` custom
    // properties already swap per `[data-theme]` on their own -- no need
    // for this component to know the theme at all, or for its tests to
    // wrap a `ThemeProvider` just to render it.
    <div
      className="rounded-2xl p-5 md:p-6"
      style={{ backgroundColor: 'var(--graph-card-bg)', border: '1px solid var(--graph-card-border)' }}
    >
      <div className="mb-1">
        <span
          className="text-[11px] font-bold uppercase tracking-wider"
          style={{ color: 'var(--graph-accent-text)' }}
        >
          Knowledge Graph
        </span>
      </div>
      <h1 className="text-page-title" style={{ color: 'var(--graph-ink)' }}>
        Graph Preview
      </h1>
      <p className="mt-1 text-sm" style={{ color: 'var(--graph-ink2)' }}>
        Entities and relationships extracted from your documents.
      </p>

      {error && (
        <div className="mt-3 flex items-center gap-3">
          <p role="alert" className="text-sm text-danger">
            {error}
          </p>
          <button
            type="button"
            onClick={fetchGraph}
            className="shrink-0 rounded-md border border-border bg-surface2 px-3 py-1.5 text-xs font-semibold text-text"
          >
            Retry
          </button>
        </div>
      )}

      {!error && isLoading && (
        <p className="mt-3 text-sm" style={{ color: 'var(--graph-ink2)' }}>
          Loading graph...
        </p>
      )}

      {/* AC8: a plain-language message, not a blank 480px canvas, for an
          account with no documents yet or none that produced entities --
          the backend can't distinguish those two cases from an empty
          result alone, and there's no reason for this copy to either. */}
      {!error && !isLoading && graph && !hasEntities && (
        <p className="mt-3 text-sm" style={{ color: 'var(--graph-ink2)' }}>
          No graph yet. Once a document reaches Ready, its entities and relationships will appear
          here.
        </p>
      )}

      {!error && !isLoading && graph && hasEntities && (
        <>
          {isCapped && (
            <p className="mt-3 text-sm" style={{ color: 'var(--graph-ink2)' }}>
              Showing the {graph.nodes.length} most-connected entities of {graph.total_node_count}{' '}
              total. Connections to entities outside this view aren't drawn.
            </p>
          )}
          <div className="mt-4">
            <GraphCanvas graph={graph} />
          </div>
        </>
      )}
    </div>
  )
}
