import { describe, expect, it, vi } from 'vitest'
import { getGraph } from './graphClient'

describe('getGraph', () => {
  it('returns the parsed body on success', async () => {
    const body = { nodes: [{ id: 'Person:A', name: 'A', type: 'Person', degree: 1 }], edges: [], total_node_count: 1 }
    const authFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))

    const result = await getGraph(authFetch)

    expect(result).toEqual(body)
    expect(authFetch).toHaveBeenCalledWith('/kg/graph')
  })

  it('returns an empty graph as-is, not as an error', async () => {
    const body = { nodes: [], edges: [], total_node_count: 0 }
    const authFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }))

    await expect(getGraph(authFetch)).resolves.toEqual(body)
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Not authenticated.' }), { status: 401 }))

    await expect(getGraph(authFetch)).rejects.toThrow('Not authenticated.')
  })

  it('throws on a 2xx body missing the expected shape', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ nodes: [] }), { status: 200 }))

    await expect(getGraph(authFetch)).rejects.toThrow('unexpected response')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(getGraph(authFetch)).rejects.toThrow('Failed to load graph (500)')
  })
})
