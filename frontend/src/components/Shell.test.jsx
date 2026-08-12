import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import Shell from './Shell'
import { useAuth } from '../context/AuthContext'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))

describe('Shell Exit handler', () => {
  it('logs out and navigates to /login when Exit is clicked', async () => {
    const logout = vi.fn()
    useAuth.mockReturnValue({ logout })
    const user = userEvent.setup()

    render(
      <MemoryRouter initialEntries={['/documents']}>
        <Routes>
          <Route path="/documents" element={<Shell />} />
          <Route path="/login" element={<div>Login page</div>} />
        </Routes>
      </MemoryRouter>,
    )

    await user.click(screen.getByRole('button', { name: /exit/i }))

    expect(logout).toHaveBeenCalledOnce()
    expect(screen.getByText('Login page')).toBeInTheDocument()
  })
})
