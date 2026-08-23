import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DocumentReadyToasts from './DocumentReadyToasts'
import { useAuth } from '../context/AuthContext'
import * as documentsClient from '../api/documentsClient'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

const PDF_DOC = {
  id: 'doc-pdf',
  filename: 'beta-report.pdf',
  file_type: 'pdf',
  file_size_bytes: 2048,
  status: 'Uploaded',
  created_at: '2026-08-12T00:00:00Z',
}

// Stands in for ChatPage so the toast's "Ask about it" CTA is observable
// (which document it preset) without pulling ChatPage's own auth/history-
// fetch mocking into these tests.
function ChatProbe() {
  const location = useLocation()
  return <div>Chat probe: {location.state?.presetDocumentId}</div>
}

function renderWatcher() {
  return render(
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route path="/documents" element={<DocumentReadyToasts />} />
        <Route path="/chat" element={<ChatProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('DocumentReadyToasts', () => {
  it('renders nothing when there is nothing to show', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([])

    const { container } = renderWatcher()
    await act(async () => {})

    expect(container).toBeEmptyDOMElement()
  })

  it('toasts when a document turns Ready mid-poll, and its CTA jumps to chat with that document preset', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments')
      .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
      .mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

    vi.useFakeTimers()
    renderWatcher()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    // Not yet Ready on the very first check -- no toast to show.
    expect(screen.queryByText('beta-report.pdf is ready')).not.toBeInTheDocument()

    // This poll's response is the Uploaded -> Ready transition.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })

    expect(screen.getByText('beta-report.pdf is ready')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ask about it' }))

    // Sync, not `findByText`: fake timers are still active here --
    // `findBy*`'s internal polling relies on real timers and would just
    // time out.
    expect(screen.getByText('Chat probe: doc-pdf')).toBeInTheDocument()
  })

  it('shows no toast for a document that was already Ready on the very first check (e.g. right after login)', async () => {
    // The whole point of this component being session-scoped: its own
    // first check, right after Shell mounts post-login, must not toast
    // for an account's entire pre-existing Ready library.
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments').mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

    const { container } = renderWatcher()
    await act(async () => {})

    expect(container).toBeEmptyDOMElement()
  })

  it('keeps checking even when nothing was pollable at the very first check, so a document uploaded moments later still gets its toast (regression)', async () => {
    // The actual bug: an earlier version only kept its interval alive
    // while the *previous* check had found something mid-pipeline, and
    // tore it down otherwise -- so a session that started with nothing
    // processing (the common case: log in, then upload something) never
    // polled again, ever, and the toast could never fire.
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments')
      .mockResolvedValueOnce([]) // nothing at all when the session starts
      .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }]) // uploaded a bit later
      .mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

    vi.useFakeTimers()
    renderWatcher()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(screen.queryByText('beta-report.pdf is ready')).not.toBeInTheDocument()

    // This check sees the freshly-uploaded document for the first time --
    // still not a transition yet, just the baseline for it.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.queryByText('beta-report.pdf is ready')).not.toBeInTheDocument()

    // This check is the actual Uploaded -> Ready transition.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.getByText('beta-report.pdf is ready')).toBeInTheDocument()
  })

  it('does not auto-dismiss -- a toast stays until the user closes it', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments')
      .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
      .mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

    vi.useFakeTimers()
    renderWatcher()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.getByText('beta-report.pdf is ready')).toBeInTheDocument()

    // Well past any of this app's other auto-dismiss durations.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10 * 60 * 1000)
    })

    expect(screen.getByText('beta-report.pdf is ready')).toBeInTheDocument()
  })

  it('dismisses its own toast when "Ask about it" is clicked, not just the X', async () => {
    // Rendered without the /documents -> /chat route swap `renderWatcher`
    // uses for the other tests here -- in the real app DocumentReadyToasts
    // lives in Shell.jsx, which never unmounts on navigation (only the
    // Outlet's content does), so this needs to prove the toast clears
    // itself while the component stays mounted, not merely because
    // navigating away tore the whole thing down.
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments')
      .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
      .mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

    vi.useFakeTimers()
    render(
      <MemoryRouter>
        <DocumentReadyToasts />
      </MemoryRouter>,
    )
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.getByText('beta-report.pdf is ready')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Ask about it' }))

    expect(screen.queryByText('beta-report.pdf is ready')).not.toBeInTheDocument()
  })

  it('dismissing a toast removes just that one', async () => {
    useAuth.mockReturnValue({ authFetch: vi.fn() })
    vi.spyOn(documentsClient, 'listDocuments')
      .mockResolvedValueOnce([{ ...PDF_DOC, status: 'Uploaded' }])
      .mockResolvedValue([{ ...PDF_DOC, status: 'Ready' }])

    vi.useFakeTimers()
    renderWatcher()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000)
    })
    expect(screen.getByText('beta-report.pdf is ready')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))

    expect(screen.queryByText('beta-report.pdf is ready')).not.toBeInTheDocument()
  })
})
