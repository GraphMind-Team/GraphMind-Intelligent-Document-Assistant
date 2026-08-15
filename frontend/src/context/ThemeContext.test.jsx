import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider, useTheme } from './ThemeContext'

function Consumer() {
  const { theme, toggleTheme, setTheme } = useTheme()
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button onClick={toggleTheme}>toggle</button>
      <button onClick={() => setTheme('dark')}>set-dark</button>
    </div>
  )
}

beforeEach(() => {
  window.localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('ThemeContext', () => {
  it('defaults to light when nothing is stored', () => {
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('reads an explicit stored override on mount', () => {
    window.localStorage.setItem('theme', 'dark')

    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('toggleTheme flips the theme, updates data-theme, and persists to localStorage', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'toggle' }))

    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(window.localStorage.getItem('theme')).toBe('dark')

    await user.click(screen.getByRole('button', { name: 'toggle' }))

    expect(screen.getByTestId('theme')).toHaveTextContent('light')
    expect(window.localStorage.getItem('theme')).toBe('light')
  })

  it('setTheme sets an explicit value directly, not just toggling', async () => {
    const user = userEvent.setup()
    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'set-dark' }))

    expect(screen.getByTestId('theme')).toHaveTextContent('dark')
  })

  it('falls back to light instead of crashing when localStorage is inaccessible', () => {
    vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError')
    })

    render(
      <ThemeProvider>
        <Consumer />
      </ThemeProvider>,
    )

    expect(screen.getByTestId('theme')).toHaveTextContent('light')

    vi.restoreAllMocks()
  })
})
