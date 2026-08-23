import { formatDetail } from './authClient'

// `authFetch` (from AuthContext) is passed in rather than imported -- same
// convention `documentsClient.js` follows, so this module never
// duplicates the auth-token/logout-on-401 behavior AuthContext.jsx
// already owns.
//
// `documentIds`, when non-empty, scopes the graph to those documents --
// forwarded as repeated `?document_ids=...&document_ids=...` params (the
// backend's `Query(default=[], ...)` shape). There's no existing
// repeated-param precedent elsewhere in this codebase to mirror
// (`chatClient.js`'s own `URLSearchParams` usage is scalar-only, via
// `.set()`) -- `.append()` in a loop is what repeated params require.
// Omitted/empty means no query string at all, so it's the exact request
// this function always sent before the filter existed.
export async function getGraph(authFetch, documentIds = []) {
  const params = new URLSearchParams()
  documentIds.forEach((id) => params.append('document_ids', id))
  const query = params.toString()

  const response = await authFetch(`/kg/graph${query ? `?${query}` : ''}`)
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
