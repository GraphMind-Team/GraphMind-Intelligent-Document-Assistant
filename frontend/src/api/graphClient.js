import { formatDetail } from './authClient'

// `authFetch` (from AuthContext) is passed in rather than imported -- same
// convention `documentsClient.js` follows, so this module never
// duplicates the auth-token/logout-on-401 behavior AuthContext.jsx
// already owns.
export async function getGraph(authFetch) {
  const response = await authFetch('/kg/graph')
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = formatDetail(data?.detail)
    throw new Error(message || `Failed to load graph (${response.status}).`)
  }

  // A 2xx response should always be this shape; a malformed body means
  // something's genuinely wrong -- fail loudly rather than handing the
  // caller `null`/partial data to render from.
  if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges) || typeof data.total_node_count !== 'number') {
    throw new Error('Failed to load graph: unexpected response.')
  }

  return data
}
