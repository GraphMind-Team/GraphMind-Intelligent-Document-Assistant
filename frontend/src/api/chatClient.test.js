import { describe, expect, it, vi } from 'vitest'
import { askQuestion, getChatHistory } from './chatClient'

const SESSION_ID = 'session-1'

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  }
}

describe('askQuestion', () => {
  it('resolves with the parsed body on a 200 with a valid shape', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { segments: [], empty_reason: 'no_documents' }))

    const result = await askQuestion(authFetch, SESSION_ID, 'q')

    expect(result).toEqual({ segments: [], empty_reason: 'no_documents' })
  })

  it('posts to the session-scoped ask endpoint', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { segments: [], empty_reason: null }))

    await askQuestion(authFetch, SESSION_ID, 'q')

    const [url] = authFetch.mock.calls[0]
    expect(url).toBe('/chat/sessions/session-1/ask')
  })

  it('flags a 503 as a service error', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(503, { detail: 'unavailable' }))

    await expect(askQuestion(authFetch, SESSION_ID, 'q')).rejects.toMatchObject({ isServiceError: true })
  })

  it('does not flag a non-503 HTTP error as a service error', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'bad question' }))

    await expect(askQuestion(authFetch, SESSION_ID, 'q')).rejects.toMatchObject({ isServiceError: false })
  })

  it('relabels a TimeoutError (AbortSignal.timeout expiring) as a timeout message, not a service error', async () => {
    const timeoutError = new DOMException('signal timed out', 'TimeoutError')
    const authFetch = vi.fn().mockRejectedValue(timeoutError)

    const error = await askQuestion(authFetch, SESSION_ID, 'q').catch((e) => e)

    expect(error.message).toMatch(/timed out/i)
    expect(error.isServiceError).toBeUndefined()
  })

  it('relabels a network TypeError as a network-failure message', async () => {
    const networkError = new TypeError('Failed to fetch')
    const authFetch = vi.fn().mockRejectedValue(networkError)

    const error = await askQuestion(authFetch, SESSION_ID, 'q').catch((e) => e)

    expect(error.message).toMatch(/network/i)
  })

  it('rethrows an unexpected error as-is, rather than mislabeling it as a network failure', async () => {
    const unexpected = new Error('expired session, please log in again')
    const authFetch = vi.fn().mockRejectedValue(unexpected)

    await expect(askQuestion(authFetch, SESSION_ID, 'q')).rejects.toBe(unexpected)
  })

  it('throws when the response body is missing a segments array', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { not_segments: true }))

    await expect(askQuestion(authFetch, SESSION_ID, 'q')).rejects.toThrow('unexpected response')
  })

  it('sends the given document_ids in the request body', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { segments: [], empty_reason: null }))

    await askQuestion(authFetch, SESSION_ID, 'q', ['doc-1', 'doc-2'])

    const [, options] = authFetch.mock.calls[0]
    expect(JSON.parse(options.body).document_ids).toEqual(['doc-1', 'doc-2'])
  })

  it('defaults document_ids to an empty array when omitted', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { segments: [], empty_reason: null }))

    await askQuestion(authFetch, SESSION_ID, 'q')

    const [, options] = authFetch.mock.calls[0]
    expect(JSON.parse(options.body).document_ids).toEqual([])
  })
})

// Story 3.4/AD-10: GET /chat/sessions/{sessionId}/history.
describe('getChatHistory', () => {
  it('resolves with the parsed body on a 200 with a valid shape', async () => {
    const page = { messages: [], next_cursor: null, has_more: false }
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, page))

    const result = await getChatHistory(authFetch, SESSION_ID)

    expect(result).toEqual(page)
  })

  it('requests the session-scoped history endpoint with no query string when cursor/limit are both omitted', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { messages: [], next_cursor: null, has_more: false }))

    await getChatHistory(authFetch, SESSION_ID)

    expect(authFetch).toHaveBeenCalledWith('/chat/sessions/session-1/history')
  })

  it('sends limit as a query param', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { messages: [], next_cursor: null, has_more: false }))

    await getChatHistory(authFetch, SESSION_ID, { limit: 3 })

    expect(authFetch).toHaveBeenCalledWith('/chat/sessions/session-1/history?limit=3')
  })

  it('sends both cursor and limit as query params when both are given', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { messages: [], next_cursor: null, has_more: false }))

    await getChatHistory(authFetch, SESSION_ID, { cursor: '2026-01-01T00:00:00|1|abc', limit: 10 })

    const [url] = authFetch.mock.calls[0]
    const query = new URLSearchParams(url.split('?')[1])
    expect(query.get('cursor')).toBe('2026-01-01T00:00:00|1|abc')
    expect(query.get('limit')).toBe('10')
  })

  it('omits an empty/falsy cursor from the query string rather than sending cursor=', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { messages: [], next_cursor: null, has_more: false }))

    await getChatHistory(authFetch, SESSION_ID, { cursor: null, limit: 3 })

    expect(authFetch).toHaveBeenCalledWith('/chat/sessions/session-1/history?limit=3')
  })

  it('surfaces the backend detail message on a non-2xx response', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'Invalid cursor.' }))

    await expect(getChatHistory(authFetch, SESSION_ID, { cursor: 'garbage' })).rejects.toThrow('Invalid cursor.')
  })

  it('throws when the response body is missing a messages array', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { not_messages: true, has_more: false }))

    await expect(getChatHistory(authFetch, SESSION_ID)).rejects.toThrow('unexpected response')
  })

  it('throws when has_more is missing from an otherwise-valid body', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { messages: [] }))

    await expect(getChatHistory(authFetch, SESSION_ID)).rejects.toThrow('unexpected response')
  })
})
