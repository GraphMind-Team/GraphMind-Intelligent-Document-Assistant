import { describe, expect, it, vi } from 'vitest'
import { createFolder, deleteFolder, listFolders, updateFolder } from './foldersClient'

describe('listFolders', () => {
  it('returns the parsed body on success', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify([{ id: 'folder-a', name: 'Contracts' }]), { status: 200 }))

    const result = await listFolders(authFetch)

    expect(result).toEqual([{ id: 'folder-a', name: 'Contracts' }])
    expect(authFetch).toHaveBeenCalledWith('/folders')
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Not authenticated.' }), { status: 401 }))

    await expect(listFolders(authFetch)).rejects.toThrow('Not authenticated.')
  })

  it('throws on a 2xx body that is not an array', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('null', { status: 200 }))

    await expect(listFolders(authFetch)).rejects.toThrow('unexpected response')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(listFolders(authFetch)).rejects.toThrow('Failed to load folders (500)')
  })
})

describe('createFolder', () => {
  it('sends a POST with the name/color body and returns the parsed response', async () => {
    const authFetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: 'folder-a', name: 'Contracts', color: 'mint' }), { status: 201 }),
    )

    const result = await createFolder(authFetch, { name: 'Contracts', color: 'mint' })

    expect(result).toEqual({ id: 'folder-a', name: 'Contracts', color: 'mint' })
    expect(authFetch).toHaveBeenCalledWith('/folders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Contracts', color: 'mint' }),
    })
  })

  it('throws the backend detail message on a 400 (blank name or invalid color)', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Folder name must not be blank.' }), { status: 400 }))

    await expect(createFolder(authFetch, { name: '', color: 'mint' })).rejects.toThrow(
      'Folder name must not be blank.',
    )
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(createFolder(authFetch, { name: 'Contracts', color: 'mint' })).rejects.toThrow(
      'Failed to create folder (500)',
    )
  })
})

describe('updateFolder', () => {
  it('sends a PATCH with the name/color body and returns the parsed response', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'folder-a', name: 'Renamed', color: 'sky' }), { status: 200 }))

    const result = await updateFolder(authFetch, 'folder-a', { name: 'Renamed', color: 'sky' })

    expect(result).toEqual({ id: 'folder-a', name: 'Renamed', color: 'sky' })
    expect(authFetch).toHaveBeenCalledWith('/folders/folder-a', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Renamed', color: 'sky' }),
    })
  })

  it('omits a field from the body entirely when not passed (partial update)', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'folder-a', name: 'Renamed' }), { status: 200 }))

    await updateFolder(authFetch, 'folder-a', { name: 'Renamed' })

    expect(authFetch).toHaveBeenCalledWith('/folders/folder-a', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'Renamed' }),
    })
  })

  it('encodes the folder id rather than interpolating it into the path raw', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ id: 'x' }), { status: 200 }))

    await updateFolder(authFetch, '../auth/me', { name: 'x' })

    expect(authFetch).toHaveBeenCalledWith(
      '/folders/..%2Fauth%2Fme',
      expect.objectContaining({ method: 'PATCH' }),
    )
  })

  it('throws the backend detail on a 404 (cross-tenant or nonexistent folder)', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Folder not found.' }), { status: 404 }))

    await expect(updateFolder(authFetch, 'folder-a', { name: 'x' })).rejects.toThrow('Folder not found.')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(updateFolder(authFetch, 'folder-a', { name: 'x' })).rejects.toThrow(
      'Failed to update folder (500)',
    )
  })
})

describe('deleteFolder', () => {
  it('sends a DELETE to the by-id path', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))

    await deleteFolder(authFetch, 'folder-a')

    expect(authFetch).toHaveBeenCalledWith('/folders/folder-a', { method: 'DELETE' })
  })

  it('encodes the folder id rather than interpolating it into the path raw', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))

    await deleteFolder(authFetch, '../auth/me')

    expect(authFetch).toHaveBeenCalledWith('/folders/..%2Fauth%2Fme', { method: 'DELETE' })
  })

  it('resolves without needing or reading a body on a real 204 response', async () => {
    const response = new Response(null, { status: 204 })
    const jsonSpy = vi.spyOn(response, 'json')
    const authFetch = vi.fn().mockResolvedValue(response)

    await expect(deleteFolder(authFetch, 'folder-a')).resolves.toBeUndefined()
    expect(jsonSpy).not.toHaveBeenCalled()
  })

  it('throws the backend detail on a 404 (cross-tenant or nonexistent folder)', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Folder not found.' }), { status: 404 }))

    await expect(deleteFolder(authFetch, 'folder-a')).rejects.toThrow('Folder not found.')
  })

  it('falls back to a generic message when a non-2xx response has no parseable body', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response('not json', { status: 500 }))

    await expect(deleteFolder(authFetch, 'folder-a')).rejects.toThrow('Failed to delete folder (500)')
  })
})
