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
    <>
      <h1 className="text-xl font-bold text-text">Graph Preview</h1>

      {error && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {error}
        </p>
      )}

      {!error && isLoading && <p className="mt-2 text-sm text-text2">Loading graph...</p>}

      {/* AC8: a plain-language message, not a blank 480px canvas, for an
          account with no documents yet or none that produced entities --
          the backend can't distinguish those two cases from an empty
          result alone, and there's no reason for this copy to either. */}
      {!error && !isLoading && graph && !hasEntities && (
        <p className="mt-2 text-sm text-text2">
          No graph yet. Once a document reaches Ready, its entities and relationships will appear
          here.
        </p>
      )}

      {!error && !isLoading && graph && hasEntities && (
        <>
          {isCapped && (
            <p className="mt-2 text-sm text-text2">
              Showing the {graph.nodes.length} most-connected entities of {graph.total_node_count}{' '}
              total. Connections to entities outside this view aren't drawn.
            </p>
          )}
          <div className="mt-4">
            <GraphCanvas graph={graph} />
          </div>
        </>
      )}
    </>
  )
}
