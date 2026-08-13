import { describe, expect, it, vi } from 'vitest'
import { askQuestion } from './chatClient'

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

    const result = await askQuestion(authFetch, 'q')

    expect(result).toEqual({ segments: [], empty_reason: 'no_documents' })
  })

  it('flags a 503 as a service error', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(503, { detail: 'unavailable' }))

    await expect(askQuestion(authFetch, 'q')).rejects.toMatchObject({ isServiceError: true })
  })

  it('does not flag a non-503 HTTP error as a service error', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'bad question' }))

    await expect(askQuestion(authFetch, 'q')).rejects.toMatchObject({ isServiceError: false })
  })

  it('relabels a TimeoutError (AbortSignal.timeout expiring) as a timeout message, not a service error', async () => {
    const timeoutError = new DOMException('signal timed out', 'TimeoutError')
    const authFetch = vi.fn().mockRejectedValue(timeoutError)

    const error = await askQuestion(authFetch, 'q').catch((e) => e)

    expect(error.message).toMatch(/timed out/i)
    expect(error.isServiceError).toBeUndefined()
  })

  it('relabels a network TypeError as a network-failure message', async () => {
    const networkError = new TypeError('Failed to fetch')
    const authFetch = vi.fn().mockRejectedValue(networkError)

    const error = await askQuestion(authFetch, 'q').catch((e) => e)

    expect(error.message).toMatch(/network/i)
  })

  it('rethrows an unexpected error as-is, rather than mislabeling it as a network failure', async () => {
    const unexpected = new Error('expired session, please log in again')
    const authFetch = vi.fn().mockRejectedValue(unexpected)

    await expect(askQuestion(authFetch, 'q')).rejects.toBe(unexpected)
  })

  it('throws when the response body is missing a segments array', async () => {
    const authFetch = vi.fn().mockResolvedValue(jsonResponse(200, { not_segments: true }))

    await expect(askQuestion(authFetch, 'q')).rejects.toThrow('unexpected response')
  })
})
