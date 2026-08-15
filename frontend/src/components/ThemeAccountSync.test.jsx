import { render } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ThemeAccountSync from './ThemeAccountSync'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'

vi.mock('../context/AuthContext', () => ({ useAuth: vi.fn() }))
vi.mock('../context/ThemeContext', () => ({ useTheme: vi.fn() }))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('ThemeAccountSync', () => {
  it('calls setTheme when accountTheme is known and differs from the local theme', () => {
    const setTheme = vi.fn()
    useAuth.mockReturnValue({ accountTheme: 'dark' })
    useTheme.mockReturnValue({ theme: 'light', setTheme })

    render(<ThemeAccountSync />)

    expect(setTheme).toHaveBeenCalledWith('dark')
  })

  it('does not call setTheme when accountTheme already matches the local theme', () => {
    const setTheme = vi.fn()
    useAuth.mockReturnValue({ accountTheme: 'light' })
    useTheme.mockReturnValue({ theme: 'light', setTheme })

    render(<ThemeAccountSync />)

    expect(setTheme).not.toHaveBeenCalled()
  })

  it('does not call setTheme while accountTheme is not known yet (null, pre-login/pre-boot-check)', () => {
    const setTheme = vi.fn()
    useAuth.mockReturnValue({ accountTheme: null })
    useTheme.mockReturnValue({ theme: 'light', setTheme })

    render(<ThemeAccountSync />)

    expect(setTheme).not.toHaveBeenCalled()
  })

  it('does not re-fire on a rerender where only the local theme changed -- the effect is keyed on accountTheme alone, so it must not fight the user\'s own subsequent toggle', () => {
    const setTheme = vi.fn()
    useAuth.mockReturnValue({ accountTheme: 'dark' })
    useTheme.mockReturnValue({ theme: 'light', setTheme })

    const { rerender } = render(<ThemeAccountSync />)
    expect(setTheme).toHaveBeenCalledTimes(1)

    // accountTheme (from AuthContext) is unchanged; only `theme` moved --
    // simulates the user toggling locally after the initial sync.
    useTheme.mockReturnValue({ theme: 'dark', setTheme })
    rerender(<ThemeAccountSync />)
    useTheme.mockReturnValue({ theme: 'light', setTheme })
    rerender(<ThemeAccountSync />)

    expect(setTheme).toHaveBeenCalledTimes(1)
  })
})
