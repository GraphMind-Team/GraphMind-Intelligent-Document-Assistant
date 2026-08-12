import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import PublicOnlyRoute from './PublicOnlyRoute'
import { useAuth } from '../context/AuthContext'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

function renderPublicOnlyRoute(initialEntry = '/login') {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<div>Login page</div>} />
        </Route>
        <Route path="/documents" element={<div>Shell content</div>} />
        <Route path="/chat" element={<div>Chat page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('PublicOnlyRoute', () => {
  it('renders nothing while AuthContext is still validating the stored token', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isInitializing: true })

    const { container } = renderPublicOnlyRoute()

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
    expect(screen.queryByText('Shell content')).not.toBeInTheDocument()
  })

  it('renders the public route (e.g. Login) when not authenticated', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isInitializing: false })

    renderPublicOnlyRoute()

    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('redirects an already-authenticated visitor to the default landing route', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isInitializing: false })

    renderPublicOnlyRoute()

    expect(screen.getByText('Shell content')).toBeInTheDocument()
  })

  it('redirects a deep-linked, already-authenticated visitor back to where they came from', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isInitializing: false })

    render(
      <MemoryRouter
        initialEntries={[{ pathname: '/login', state: { from: { pathname: '/chat', search: '', hash: '' } } }]}
      >
        <Routes>
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<div>Login page</div>} />
          </Route>
          <Route path="/documents" element={<div>Shell content</div>} />
          <Route path="/chat" element={<div>Chat page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Chat page')).toBeInTheDocument()
  })
})
