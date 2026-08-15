import { describe, expect, it, vi } from 'vitest'
import { updateTheme } from './settingsClient'

describe('updateTheme', () => {
  it('sends a PATCH with the theme body and returns the parsed response', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ theme: 'dark' }), { status: 200 }))

    const result = await updateTheme(authFetch, 'dark')

    expect(result).toEqual({ theme: 'dark' })
    expect(authFetch).toHaveBeenCalledWith('/auth/theme', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: 'dark' }),
    })
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Not authenticated.' }), { status: 401 }))

    await expect(updateTheme(authFetch, 'dark')).rejects.toThrow('Not authenticated.')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(updateTheme(authFetch, 'dark')).rejects.toThrow('Failed to save theme (500)')
  })
})
