import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import MessageActions from './MessageActions'
import * as chatClient from '../../api/chatClient'

afterEach(() => {
  vi.restoreAllMocks()
})

// jsdom exposes `navigator.clipboard` as a getter-only accessor (no
// setter), so a plain `Object.assign`/property set throws -- `writeText`
// itself is `undefined` there since jsdom doesn't implement the Clipboard
// API. Must run *after* `userEvent.setup()`: that call installs its own
// clipboard stub, which would otherwise clobber this one if set up first.
function stubClipboard() {
  const writeText = vi.fn().mockResolvedValue(undefined)
  Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  return writeText
}

function renderActions(props = {}) {
  return render(
    <MessageActions
      authFetch={vi.fn()}
      messageId="msg-1"
      initialFeedback={null}
      answerText="TechCorp's refund window is 30 days."
      {...props}
    />,
  )
}

describe('MessageActions', () => {
  it('copies the plain answer text to the clipboard and shows a confirmation', async () => {
    const user = userEvent.setup()
    const writeText = stubClipboard()
    renderActions()

    await user.click(screen.getByRole('button', { name: 'Copy answer' }))

    expect(writeText).toHaveBeenCalledWith("TechCorp's refund window is 30 days.")
    expect(await screen.findByRole('button', { name: 'Copied!' })).toBeInTheDocument()
  })

  it('leaves the button unconfirmed, without throwing, when the clipboard write is denied', async () => {
    const user = userEvent.setup()
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockRejectedValue(new DOMException('Document is not focused.', 'NotAllowedError')) },
      configurable: true,
    })
    renderActions()

    await user.click(screen.getByRole('button', { name: 'Copy answer' }))

    expect(screen.getByRole('button', { name: 'Copy answer' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Copied!' })).not.toBeInTheDocument()
  })

  it('rates the answer up and sends the rating to the backend', async () => {
    const setFeedback = vi.spyOn(chatClient, 'setMessageFeedback').mockResolvedValue({ id: 'msg-1', feedback: 'up' })
    const user = userEvent.setup()
    const authFetch = vi.fn()
    renderActions({ authFetch })

    const thumbsUp = screen.getByRole('button', { name: 'Good answer' })
    await user.click(thumbsUp)

    expect(thumbsUp).toHaveAttribute('aria-pressed', 'true')
    await waitFor(() => expect(setFeedback).toHaveBeenCalledWith(authFetch, 'msg-1', 'up'))
  })

  it('clicking the already-active thumb clears the rating instead of toggling', async () => {
    const setFeedback = vi.spyOn(chatClient, 'setMessageFeedback').mockResolvedValue({ id: 'msg-1', feedback: null })
    const user = userEvent.setup()
    renderActions({ initialFeedback: 'up' })

    const thumbsUp = screen.getByRole('button', { name: 'Marked as a good answer' })
    expect(thumbsUp).toHaveAttribute('aria-pressed', 'true')

    await user.click(thumbsUp)

    expect(thumbsUp).toHaveAttribute('aria-pressed', 'false')
    await waitFor(() => expect(setFeedback).toHaveBeenLastCalledWith(expect.anything(), 'msg-1', null))
  })

  it('switching from down to up sends "up", not a toggle-off', async () => {
    const setFeedback = vi.spyOn(chatClient, 'setMessageFeedback').mockResolvedValue({ id: 'msg-1', feedback: 'up' })
    const user = userEvent.setup()
    renderActions({ initialFeedback: 'down' })

    await user.click(screen.getByRole('button', { name: 'Good answer' }))

    expect(screen.getByRole('button', { name: 'Marked as a good answer' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Bad answer' })).toHaveAttribute('aria-pressed', 'false')
    await waitFor(() => expect(setFeedback).toHaveBeenLastCalledWith(expect.anything(), 'msg-1', 'up'))
  })

  it('rolls back the optimistic rating and shows an error on a failed save', async () => {
    vi.spyOn(chatClient, 'setMessageFeedback').mockRejectedValue(new Error('Failed to save feedback (500).'))
    const user = userEvent.setup()
    renderActions()

    const thumbsDown = screen.getByRole('button', { name: 'Bad answer' })
    await user.click(thumbsDown)

    expect(await screen.findByRole('alert')).toHaveTextContent('Failed to save feedback (500).')
    expect(thumbsDown).toHaveAttribute('aria-pressed', 'false')
  })

  it('does not call the backend when there is no message id', async () => {
    const setFeedback = vi.spyOn(chatClient, 'setMessageFeedback')
    const user = userEvent.setup()
    renderActions({ messageId: null })

    await user.click(screen.getByRole('button', { name: 'Good answer' }))

    expect(setFeedback).not.toHaveBeenCalled()
  })
})
