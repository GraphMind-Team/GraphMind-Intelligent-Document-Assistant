import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import RobotMascot from './RobotMascot'

describe('RobotMascot', () => {
  it('is aria-hidden -- decorative and non-interactive', () => {
    const { container } = render(<RobotMascot />)

    expect(container.firstChild).toHaveAttribute('aria-hidden', 'true')
  })

  it('references the theme-aware shadow tokens, not a hardcoded light-mode-only rgba', () => {
    const { container } = render(<RobotMascot />)

    const shadowedEls = Array.from(container.querySelectorAll('[class*="shadow-"]'))
    expect(shadowedEls.length).toBeGreaterThan(0)
    for (const el of shadowedEls) {
      expect(el.className).toMatch(/shadow-\[var\(--robot-shadow-(head|body)\)\]/)
      // A raw rgba(10,46,99,...) here would stay navy-tinted in dark mode
      // instead of switching to the theme's neutral-black override.
      expect(el.className).not.toMatch(/rgba\(/)
    }
  })
})
