import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import CitationChip from './CitationChip'

// One "sources" pill per assistant message -- replaces the old
// one-chip-per-citation inline layout, which put a chip after every
// segment and read as cluttered on a multi-segment answer. `citations` is
// already deduped (by chapter+document) and flattened across every
// segment by ChatMessage, so a message that cites the same chapter twice
// still shows one entry here.
//
// Toggle/outside-click/Escape mechanics mirror DocumentCard.jsx's "⋮"
// menu -- this project's one established popover primitive -- but the
// panel itself holds only static `<cite>` chips, not actionable items
// (jump-to-source is still out of scope, same as CitationChip's own
// contract), so it's a plain labelled group rather than a `role="menu"`.
export default function CitationSummary({ citations }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const buttonRef = useRef(null)
  const panelRef = useRef(null)

  // Outside-click needs a document-level listener -- there's no local
  // event for "a click landed outside this element". Scoped to only run
  // while the panel is actually open, mirroring DocumentCard.jsx's own
  // menu-open-gated effect.
  useEffect(() => {
    if (!isOpen) return undefined

    function handlePointerDown(event) {
      if (panelRef.current?.contains(event.target)) return
      if (buttonRef.current?.contains(event.target)) return
      setIsOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    return () => document.removeEventListener('mousedown', handlePointerDown)
  }, [isOpen])

  function handleKeyDown(event) {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    setIsOpen(false)
    buttonRef.current?.focus()
  }

  if (citations.length === 0) return null

  return (
    <div className="relative mt-2 inline-block" onKeyDown={handleKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="true"
        aria-expanded={isOpen}
        onClick={() => setIsOpen((open) => !open)}
        className="inline-flex items-center gap-1.5 rounded-full bg-citation px-3 py-1 text-[11.5px] font-bold text-citation-text hover:opacity-80"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-3 w-3 shrink-0"
        >
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z" />
          <path d="M14 2v6h6" />
        </svg>
        {t('chat.sources.toggleLabel', { count: citations.length })}
      </button>

      {isOpen && (
        <div
          ref={panelRef}
          role="group"
          aria-label={t('chat.sources.panelAria')}
          className="absolute left-0 top-full z-10 mt-1 min-w-[220px] max-w-[320px] rounded-lg border border-border bg-card-bg py-2 shadow-modal"
        >
          <ul className="m-0 list-none space-y-1.5 p-0 px-3">
            {citations.map((citation, index) => (
              <li key={index}>
                <CitationChip chapter={citation.chapter} documentFilename={citation.documentFilename} />
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
