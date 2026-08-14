import { createContext, useCallback, useContext, useState } from 'react'

// Chat document-scope state (Story 3.3, AD-5 -- AGENTS.md names this
// explicitly as context-owned state, never prop-drilled, never Redux).
// Shared between DocumentsScopePanel (which owns the fetched document
// list) and ChatPage (which reads the current selection when a question
// is submitted). Holds only the selected ids -- the document list itself
// stays local to DocumentsScopePanel, since only it needs the full
// filename/status data.
const ChatScopeContext = createContext(undefined)

export function ChatScopeProvider({ children }) {
  const [selectedDocumentIds, setSelectedDocumentIds] = useState([])

  // No separate "apply" step (UX-DR9) -- every call here is immediately
  // reflected in `selectedDocumentIds`, which is exactly what the next
  // `askQuestion` call reads.
  const toggleDocument = useCallback((id) => {
    setSelectedDocumentIds((prev) =>
      prev.includes(id) ? prev.filter((existing) => existing !== id) : [...prev, id],
    )
  }, [])

  // Replaces the selection outright with the given ids -- the caller
  // (DocumentsScopePanel's "Select all") is responsible for deciding which
  // ids that is (every Ready document, per UX-DR10), not this context.
  const selectAll = useCallback((ids) => setSelectedDocumentIds(ids), [])

  // A safety net, not a fix for a live bug: `ChatScopeProvider` lives
  // inside ChatPage, so navigating away and back already resets the
  // selection to empty by unmounting the provider. This only matters if
  // DocumentsScopePanel is ever refetched again within the same mount (no
  // such refetch exists yet) -- called there so a stale id (deleted, or
  // regressed from Ready) can't silently narrow a future scope to
  // nothing.
  const retainOnly = useCallback((validIds) => {
    const valid = new Set(validIds)
    setSelectedDocumentIds((prev) => prev.filter((id) => valid.has(id)))
  }, [])

  const value = { selectedDocumentIds, toggleDocument, selectAll, retainOnly }
  return <ChatScopeContext.Provider value={value}>{children}</ChatScopeContext.Provider>
}

export function useChatScope() {
  const ctx = useContext(ChatScopeContext)
  if (ctx === undefined) {
    throw new Error('useChatScope must be used within a ChatScopeProvider')
  }
  return ctx
}
