import { Outlet } from 'react-router-dom'
import { ChatSessionsProvider } from '../context/ChatSessionsContext'

// Layout route (multi-session chat): wraps both `/chat` (ChatIndexRedirect)
// and `/chat/:sessionId` (ChatPage) in one `ChatSessionsProvider`, mirroring
// Shell.jsx's own layout-route shape -- a provider has to sit above both
// routes so the redirect and the real page share one sessions-list fetch
// instead of each mounting its own.
export default function ChatSessionsLayout() {
  return (
    <ChatSessionsProvider>
      <Outlet />
    </ChatSessionsProvider>
  )
}
