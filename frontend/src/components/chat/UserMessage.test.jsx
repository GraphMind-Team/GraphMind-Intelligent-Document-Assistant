import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import UserMessage from './UserMessage'

afterEach(() => {
  vi.restoreAllMocks()
})

// jsdom exposes `navigator.clipboard` as a getter-only accessor -- see
// MessageActions.test.jsx's own comment for why this must run after
// `userEvent.setup()`.
function stubClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  return writeText
}

function renderMessage(props = {}) {
  return render(
    <UserMessage id="user-msg-1" text="What is the refund window?" onEditMessage={vi.fn()} {...props} />,
  )
}

describe('UserMessage', () => {
  it('renders the message text', () => {
    renderMessage()
    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
  })

  it('copies its own text to the clipboard and shows a confirmation', async () => {
    const user = userEvent.setup()
    const writeText = stubClipboard()
    renderMessage()

    await user.click(screen.getByRole('button', { name: 'Copy your message' }))

    expect(writeText).toHaveBeenCalledWith('What is the refund window?')
    expect(await screen.findByRole('button', { name: 'Copied!' })).toBeInTheDocument()
  })

  it('hides the edit button while there is no message id yet', () => {
    renderMessage({ id: null })
    expect(screen.queryByRole('button', { name: 'Edit your message' })).not.toBeInTheDocument()
    // Copy still works regardless -- no id gate on it.
    expect(screen.getByRole('button', { name: 'Copy your message' })).toBeInTheDocument()
  })

  it('clicking edit swaps the bubble for an editable textarea pre-filled with the current text', async () => {
    const user = userEvent.setup()
    renderMessage()

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))

    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    expect(textarea).toHaveValue('What is the refund window?')
    // The static (non-editable) bubble is gone -- Copy/Edit only exist on
    // that display-mode bubble.
    expect(screen.queryByRole('button', { name: 'Copy your message' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Edit your message' })).not.toBeInTheDocument()
  })

  it('Enter commits the edit and calls onEditMessage with the trimmed text', async () => {
    const onEditMessage = vi.fn()
    const user = userEvent.setup()
    renderMessage({ onEditMessage })

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))
    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    await user.clear(textarea)
    await user.type(textarea, '  What is the warranty period?  {Enter}')

    expect(onEditMessage).toHaveBeenCalledWith('user-msg-1', 'What is the warranty period?')
  })

  it('the Save button commits the edit the same way Enter does', async () => {
    const onEditMessage = vi.fn()
    const user = userEvent.setup()
    renderMessage({ onEditMessage })

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))
    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    await user.clear(textarea)
    await user.type(textarea, 'What is the warranty period?')
    await user.click(screen.getByRole('button', { name: 'Save' }))

    expect(onEditMessage).toHaveBeenCalledWith('user-msg-1', 'What is the warranty period?')
  })

  it('Shift+Enter inserts a newline instead of committing', async () => {
    const onEditMessage = vi.fn()
    const user = userEvent.setup()
    renderMessage({ onEditMessage })

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))
    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    await user.clear(textarea)
    await user.type(textarea, 'line one{Shift>}{Enter}{/Shift}line two')

    expect(onEditMessage).not.toHaveBeenCalled()
    expect(textarea).toHaveValue('line one\nline two')
  })

  it('does not commit a blank/whitespace-only edit', async () => {
    const onEditMessage = vi.fn()
    const user = userEvent.setup()
    renderMessage({ onEditMessage })

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))
    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    await user.clear(textarea)
    await user.type(textarea, '   {Enter}')

    expect(onEditMessage).not.toHaveBeenCalled()
    expect(textarea).toBeInTheDocument()
  })

  it('Escape cancels the edit and restores the original text, discarding the draft', async () => {
    const onEditMessage = vi.fn()
    const user = userEvent.setup()
    renderMessage({ onEditMessage })

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))
    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    await user.clear(textarea)
    await user.type(textarea, 'a discarded draft{Escape}')

    expect(onEditMessage).not.toHaveBeenCalled()
    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: 'Edit your message' })).not.toBeInTheDocument()
  })

  it('the Cancel button discards the draft the same way Escape does', async () => {
    const onEditMessage = vi.fn()
    const user = userEvent.setup()
    renderMessage({ onEditMessage })

    await user.click(screen.getByRole('button', { name: 'Edit your message' }))
    const textarea = screen.getByRole('textbox', { name: 'Edit your message' })
    await user.clear(textarea)
    await user.type(textarea, 'a discarded draft')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onEditMessage).not.toHaveBeenCalled()
    expect(screen.getByText('What is the refund window?')).toBeInTheDocument()
  })
})
