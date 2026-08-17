import { describe, expect, it, vi } from 'vitest'
import { changePassword, deleteAccount, updateProfile, updateTheme } from './settingsClient'

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

describe('updateProfile', () => {
  it('sends a PATCH with the full_name body and returns the parsed response', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ full_name: 'Maria Petrova' }), { status: 200 }))

    const result = await updateProfile(authFetch, { fullName: 'Maria Petrova' })

    expect(result).toEqual({ full_name: 'Maria Petrova' })
    expect(authFetch).toHaveBeenCalledWith('/auth/me', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ full_name: 'Maria Petrova' }),
    })
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'full_name must not be blank' }), { status: 422 }))

    await expect(updateProfile(authFetch, { fullName: '' })).rejects.toThrow('full_name must not be blank')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(updateProfile(authFetch, { fullName: 'Maria Petrova' })).rejects.toThrow(
      'Failed to save profile (500)',
    )
  })
})

describe('changePassword', () => {
  it('sends a POST with the current/new password body and returns the parsed response', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Password updated.' }), { status: 200 }))

    const result = await changePassword(authFetch, {
      currentPassword: 'old-password',
      newPassword: 'new-password',
    })

    expect(result).toEqual({ detail: 'Password updated.' })
    expect(authFetch).toHaveBeenCalledWith('/auth/me/password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: 'old-password', new_password: 'new-password' }),
    })
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Current password is incorrect.' }), { status: 400 }))

    await expect(
      changePassword(authFetch, { currentPassword: 'wrong', newPassword: 'new-password' }),
    ).rejects.toThrow('Current password is incorrect.')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(
      changePassword(authFetch, { currentPassword: 'old-password', newPassword: 'new-password' }),
    ).rejects.toThrow('Failed to change password (500)')
  })
})

describe('deleteAccount', () => {
  it('sends a DELETE to /auth/me', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))

    await deleteAccount(authFetch)

    expect(authFetch).toHaveBeenCalledWith('/auth/me', { method: 'DELETE' })
  })

  it('resolves without needing or reading a body on a real 204 response', async () => {
    // Mirrors documentsClient.test.js's deleteDocument coverage of the same
    // shape -- a genuine empty-body Response, not a mock that happens to
    // have a `.json()`. Catches a regression where deleteAccount started
    // unconditionally calling `response.json()`, which a test that only
    // mocks the whole module (as DeleteAccountCard.test.jsx does) never
    // exercises.
    const response = new Response(null, { status: 204 })
    const jsonSpy = vi.spyOn(response, 'json')
    const authFetch = vi.fn().mockResolvedValue(response)

    await expect(deleteAccount(authFetch)).resolves.toBeUndefined()
    expect(jsonSpy).not.toHaveBeenCalled()
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: "Document is still being processed and can't be deleted yet." }),
        { status: 409 },
      ),
    )

    await expect(deleteAccount(authFetch)).rejects.toThrow(
      "Document is still being processed and can't be deleted yet.",
    )
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(deleteAccount(authFetch)).rejects.toThrow('Failed to delete account (500)')
  })
})
