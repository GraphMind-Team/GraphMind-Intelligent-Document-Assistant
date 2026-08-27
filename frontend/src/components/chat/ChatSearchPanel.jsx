import { useTranslation } from 'react-i18next'

// Search within the conversation (sits above the documents-in-scope
// panel in ChatPage's right column). Filters the thread that is already
// loaded -- deliberately not a server-side history search, so it never
// silently changes what "Load earlier messages" means; the hint below
// says so rather than letting an empty result read as "you never asked
// that".
//
// Typing filters live; the surrounding <form> exists so pressing Enter
// is a no-op submit instead of bubbling out of the input (and so the
// field is a real search landmark for assistive tech).
//
// A match no longer removes every other message from the thread (that
// hid the surrounding conversation instead of helping find something in
// it) -- the thread stays intact and this panel's prev/next arrows
// scroll the active match into view instead, `activeMatchNumber` (1-based)
// tracking which of the `resultCount` matches that is.
export default function ChatSearchPanel({
  value,
  onChange,
  resultCount,
  activeMatchNumber,
  onPrevMatch,
  onNextMatch,
}) {
  const { t } = useTranslation()
  return (
    <section className="w-full shrink-0 self-start rounded-2xl border border-border bg-card-bg p-5 shadow-card">
      <h2 className="mb-2.5 text-[13px] font-bold text-primary">{t('chat.searchPanel.title')}</h2>

      <form role="search" onSubmit={(event) => event.preventDefault()}>
        <label htmlFor="chat-search" className="sr-only">
          {t('chat.searchPanel.title')}
        </label>
        <div className="relative">
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-text2"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            id="chat-search"
            type="search"
            value={value}
            onChange={(event) => onChange(event.target.value)}
            placeholder={t('chat.searchPanel.placeholder')}
            className="w-full min-w-0 rounded-full border border-border py-2 pl-9 pr-3.5 text-[12px]"
          />
        </div>
      </form>

      {value.trim() !== '' && (
        <div className="mt-2 flex items-center justify-between gap-2">
          {/* aria-live: the count is the only feedback that a query matched
              anything, and the thread itself is a separate live region the
              search deliberately doesn't re-announce. */}
          <p aria-live="polite" className="text-[11px] text-text2">
            {resultCount === 0
              ? t('chat.searchPanel.noMatches')
              : t('chat.searchPanel.matchStatus', { active: activeMatchNumber, result: resultCount })}
          </p>

          {resultCount > 0 && (
            <div className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={onPrevMatch}
                aria-label={t('chat.searchPanel.prevMatch')}
                className="btn-ghost flex h-6 w-6 items-center justify-center rounded-full"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-3.5 w-3.5"
                >
                  <path d="M18 15l-6-6-6 6" />
                </svg>
              </button>
              <button
                type="button"
                onClick={onNextMatch}
                aria-label={t('chat.searchPanel.nextMatch')}
                className="btn-ghost flex h-6 w-6 items-center justify-center rounded-full"
              >
                <svg
                  aria-hidden="true"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="h-3.5 w-3.5"
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
