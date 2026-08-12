import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import ProtectedRoute from './ProtectedRoute'
import { useAuth } from '../context/AuthContext'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

function renderProtectedRoute() {
  return render(
    <MemoryRouter initialEntries={['/documents']}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/documents" element={<div>Shell content</div>} />
        </Route>
        <Route path="/login" element={<div>Login page</div>} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProtectedRoute', () => {
  it('renders nothing while AuthContext is still validating the stored token', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isInitializing: true })

    const { container } = renderProtectedRoute()

    expect(container).toBeEmptyDOMElement()
    expect(screen.queryByText('Shell content')).not.toBeInTheDocument()
    expect(screen.queryByText('Login page')).not.toBeInTheDocument()
  })

  it('redirects to /login when not authenticated', () => {
    useAuth.mockReturnValue({ isAuthenticated: false, isInitializing: false })

    renderProtectedRoute()

    expect(screen.getByText('Login page')).toBeInTheDocument()
  })

  it('renders the protected route when authenticated', () => {
    useAuth.mockReturnValue({ isAuthenticated: true, isInitializing: false })

    renderProtectedRoute()

    expect(screen.getByText('Shell content')).toBeInTheDocument()
  })
})
