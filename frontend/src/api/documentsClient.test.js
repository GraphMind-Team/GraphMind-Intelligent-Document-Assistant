import { afterEach, describe, expect, it, vi } from 'vitest'
import { listDocuments, uploadDocument, validateFile } from './documentsClient'

describe('validateFile', () => {
  function makeFile(name, size, type = 'application/octet-stream') {
    const file = new File([new Uint8Array(Math.max(size, 0))], name, { type })
    // jsdom's File constructor derives size from the blob content; override
    // directly so large-size cases don't require allocating real bytes.
    Object.defineProperty(file, 'size', { value: size })
    return file
  }

  it('accepts a .pdf under the 20MB limit', () => {
    expect(validateFile(makeFile('report.pdf', 1024))).toBeNull()
  })

  it('accepts .md, .markdown, .html, .htm', () => {
    expect(validateFile(makeFile('notes.md', 100))).toBeNull()
    expect(validateFile(makeFile('notes.markdown', 100))).toBeNull()
    expect(validateFile(makeFile('page.html', 100))).toBeNull()
    expect(validateFile(makeFile('page.htm', 100))).toBeNull()
  })

  it('rejects an unsupported format with a reason naming the supported formats', () => {
    const reason = validateFile(makeFile('resume.docx', 100))
    expect(reason).toContain('Unsupported file format')
    expect(reason).toContain('.pdf')
  })

  it('rejects a file over 20MB with a reason naming the 20MB limit', () => {
    const reason = validateFile(makeFile('big.pdf', 20 * 1024 * 1024 + 1))
    expect(reason).toContain('20MB')
  })

  it('accepts a file exactly at the 20MB limit', () => {
    expect(validateFile(makeFile('exact.pdf', 20 * 1024 * 1024))).toBeNull()
  })
})

describe('listDocuments', () => {
  it('returns the parsed body on success', async () => {
    const authFetch = vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: '1' }]), { status: 200 }))
    const result = await listDocuments(authFetch)
    expect(result).toEqual([{ id: '1' }])
    expect(authFetch).toHaveBeenCalledWith('/documents')
  })

  it('throws the backend detail message on failure', async () => {
    const authFetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify({ detail: 'Not authenticated.' }), { status: 401 }))
    await expect(listDocuments(authFetch)).rejects.toThrow('Not authenticated.')
  })
})

describe('uploadDocument', () => {
  // jsdom's XMLHttpRequest doesn't perform real network I/O, so a small
  // scripted fake stands in -- it exercises the same open/setRequestHeader/
  // upload.progress/load/send call sequence uploadDocument relies on.
  class FakeXHR {
    constructor() {
      this._uploadHandlers = {}
      this.upload = { addEventListener: (event, handler) => (this._uploadHandlers[event] = handler) }
      this._handlers = {}
      this.status = 0
      this.responseText = ''
      FakeXHR.lastInstance = this
    }
    open(method, url) {
      this.method = method
      this.url = url
    }
    setRequestHeader(name, value) {
      this.headers = { ...(this.headers || {}), [name]: value }
    }
    addEventListener(event, handler) {
      this._handlers[event] = handler
    }
    send(body) {
      this.sentBody = body
    }
  }

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('resolves with the parsed response body on a 2xx status, and reports progress', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXHR)

    const onProgress = vi.fn()
    const file = new File(['content'], 'report.pdf', { type: 'application/pdf' })
    const promise = uploadDocument('a-token', file, onProgress)
    const xhrInstance = FakeXHR.lastInstance

    expect(xhrInstance.headers.Authorization).toBe('Bearer a-token')
    xhrInstance._uploadHandlers.progress({ lengthComputable: true, loaded: 50, total: 100 })
    expect(onProgress).toHaveBeenCalledWith(50)

    xhrInstance.status = 201
    xhrInstance.responseText = JSON.stringify({ id: 'doc-1', status: 'Uploaded' })
    xhrInstance._handlers.load()

    await expect(promise).resolves.toEqual({ id: 'doc-1', status: 'Uploaded' })
  })

  it('rejects with the backend detail message on a non-2xx status', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXHR)

    const file = new File(['content'], 'resume.docx')
    const promise = uploadDocument('a-token', file, vi.fn())
    const xhrInstance = FakeXHR.lastInstance

    xhrInstance.status = 400
    xhrInstance.responseText = JSON.stringify({ detail: 'Unsupported file format. Supported formats: .pdf.' })
    xhrInstance._handlers.load()

    await expect(promise).rejects.toThrow('Unsupported file format')
  })

  it('rejects on a transport error', async () => {
    vi.stubGlobal('XMLHttpRequest', FakeXHR)

    const file = new File(['content'], 'report.pdf', { type: 'application/pdf' })
    const promise = uploadDocument('a-token', file, vi.fn())
    const xhrInstance = FakeXHR.lastInstance

    xhrInstance._handlers.error()

    await expect(promise).rejects.toThrow('Upload failed')
  })
})
