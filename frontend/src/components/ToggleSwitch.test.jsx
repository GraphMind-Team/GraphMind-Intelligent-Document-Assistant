import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ToggleSwitch from './ToggleSwitch'

describe('ToggleSwitch', () => {
  it('exposes role=switch and reflects checked via aria-checked', () => {
    render(<ToggleSwitch checked={true} onChange={() => {}} label="Dark mode" />)

    const toggle = screen.getByRole('switch', { name: 'Dark mode' })
    expect(toggle).toHaveAttribute('aria-checked', 'true')
  })

  it('calls onChange with the flipped value on click', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ToggleSwitch checked={false} onChange={onChange} label="Dark mode" />)

    await user.click(screen.getByRole('switch', { name: 'Dark mode' }))

    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('activates via keyboard (Enter/Space), same as any native button', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ToggleSwitch checked={false} onChange={onChange} label="Dark mode" />)

    screen.getByRole('switch', { name: 'Dark mode' }).focus()
    await user.keyboard('{Enter}')

    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('no-ops on click while disabled, but stays focusable (aria-disabled, not the native disabled attribute)', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<ToggleSwitch checked={false} onChange={onChange} disabled label="Dark mode" />)

    const toggle = screen.getByRole('switch', { name: 'Dark mode' })
    expect(toggle).toHaveAttribute('aria-disabled', 'true')
    expect(toggle).not.toHaveAttribute('disabled')

    await user.click(toggle)

    expect(onChange).not.toHaveBeenCalled()
  })
})
