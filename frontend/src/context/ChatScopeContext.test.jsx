import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { ChatScopeProvider, useChatScope } from './ChatScopeContext'

function ThrowsOutsideProvider() {
  useChatScope()
  return null
}

function Consumer() {
  const { selectedDocumentIds, toggleDocument, selectAll, retainOnly } = useChatScope()
  return (
    <div>
      <p data-testid="selected">{selectedDocumentIds.join(',')}</p>
      <button onClick={() => toggleDocument('doc-1')}>toggle doc-1</button>
      <button onClick={() => toggleDocument('doc-2')}>toggle doc-2</button>
      <button onClick={() => selectAll(['doc-1', 'doc-2', 'doc-3'])}>select all</button>
      <button onClick={() => retainOnly(['doc-1'])}>retain doc-1 only</button>
    </div>
  )
}

describe('ChatScopeContext', () => {
  it('throws when useChatScope is used outside a ChatScopeProvider', () => {
    // React logs its own error to the console for a thrown render -- not
    // asserted here, only that the hook itself throws the intended message.
    expect(() => render(<ThrowsOutsideProvider />)).toThrow(
      'useChatScope must be used within a ChatScopeProvider',
    )
  })

  it('starts with an empty selection', () => {
    render(
      <ChatScopeProvider>
        <Consumer />
      </ChatScopeProvider>,
    )

    expect(screen.getByTestId('selected')).toHaveTextContent('')
  })

  it('toggleDocument adds then removes an id', async () => {
    const user = userEvent.setup()
    render(
      <ChatScopeProvider>
        <Consumer />
      </ChatScopeProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'toggle doc-1' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('doc-1')

    await user.click(screen.getByRole('button', { name: 'toggle doc-1' }))
    expect(screen.getByTestId('selected')).toHaveTextContent('')
  })

  it('selectAll replaces the selection with the given list', async () => {
    const user = userEvent.setup()
    render(
      <ChatScopeProvider>
        <Consumer />
      </ChatScopeProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'toggle doc-2' }))
    await user.click(screen.getByRole('button', { name: 'select all' }))

    expect(screen.getByTestId('selected')).toHaveTextContent('doc-1,doc-2,doc-3')
  })

  it('retainOnly drops ids not in the given list and keeps the rest', async () => {
    const user = userEvent.setup()
    render(
      <ChatScopeProvider>
        <Consumer />
      </ChatScopeProvider>,
    )

    await user.click(screen.getByRole('button', { name: 'select all' }))
    await user.click(screen.getByRole('button', { name: 'retain doc-1 only' }))

    expect(screen.getByTestId('selected')).toHaveTextContent('doc-1')
  })
})
