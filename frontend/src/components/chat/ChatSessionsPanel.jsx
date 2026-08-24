import { useTranslation } from 'react-i18next'

// Left "chats" panel (visual-only placeholder): the backend has exactly one
// continuous chat thread per user today, no session/chat-id concept at all
// -- so this mirrors DocumentsScopePanel's shell/tokens for a consistent
// look, but "New chat" stays a disabled, aria-disabled affordance and the
// list shows only the one real thread that already exists. Wiring this up
// to real, switchable chat sessions needs new backend surface first.
export default function ChatSessionsPanel() {
  const { t } = useTranslation()

  return (
    <aside className="w-full shrink-0 self-start rounded-2xl border border-border bg-card-bg p-5 shadow-card min-[901px]:w-[260px]">
      <h2 className="mb-2.5 text-[13px] font-bold text-primary">{t('chat.sessionsPanel.title')}</h2>

      <button
        type="button"
        aria-disabled="true"
        title={t('chat.sessionsPanel.newChatComingSoon')}
        className="mb-3 flex w-full cursor-not-allowed items-center justify-center gap-1.5 rounded-full border border-border bg-surface2 px-3.5 py-2 text-[12.5px] font-semibold text-text2"
      >
        <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-3.5 w-3.5">
          <path d="M12 5v14M5 12h14" />
        </svg>
        {t('chat.sessionsPanel.newChat')}
      </button>

      <ul className="list-none space-y-1.5 p-0">
        <li className="flex items-center gap-2 rounded-xl border border-accent/40 bg-accent/10 px-3 py-2.5 text-[12.5px] font-semibold text-accent">
          <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="h-4 w-4 shrink-0">
            <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
          </svg>
          <span className="min-w-0 flex-1 truncate">{t('chat.sessionsPanel.currentChat')}</span>
        </li>
      </ul>

      <p className="mt-3 text-[11px] text-text2">{t('chat.sessionsPanel.note')}</p>
    </aside>
  )
}
