import { describe, expect, it, vi } from 'vitest'
import { changePassword, updateProfile, updateTheme } from './settingsClient'

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
