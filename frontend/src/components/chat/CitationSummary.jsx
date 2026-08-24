import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useTranslation } from 'react-i18next'
import CitationChip from './CitationChip'

// Widest the panel is ever allowed to render -- mirrors the `max-w-[320px]`
// this panel has always carried; kept as a constant here too since the
// portal's own viewport-clamping math (below) needs the same number the
// className sets, not a second, independently-tuned guess.
const PANEL_MAX_WIDTH = 320
// Space kept clear between the panel and the viewport edge it's closest
// to, purely so a clamped panel never touches the edge pixel-for-pixel.
const VIEWPORT_MARGIN = 8

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
//
// The open panel is portalled to `document.body`, not rendered inline
// here -- the sources pill sits in the actions row *below* the answer
// bubble (ChatMessage.jsx's own "actions live outside the bubble"
// layout), and that row's ancestor message wrapper carries `anim-rise`,
// whose entrance animation keeps a live `transform` on the element for
// its duration. Per the CSS stacking-context spec, an active `transform`
// forms a new stacking context -- so this panel's own `z-index: 10`
// only ever wins *inside* its own message's stacking context; a *later*
// message's bubble, animating in below it, forms its own competing
// context and paints on top regardless, covering an still-open panel
// from an earlier message (verified by hand: the panel's ancestor chain
// showed exactly this). A portal escapes every ancestor's stacking
// context entirely, the same reason `DocumentCard.jsx`'s own modals are
// portalled (see that file's comment) -- `position: fixed` coordinates
// computed from the toggle button's own `getBoundingClientRect()`
// replace the old `absolute left-0 top-full` positioning that relied on
// being a normal-flow descendant of that button.
export default function CitationSummary({ citations }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [position, setPosition] = useState(null)
  const buttonRef = useRef(null)
  const panelRef = useRef(null)

  // Computed fresh every time the panel opens (button position can shift
  // between opens -- new messages appended above/below, a window resize,
  // etc.) -- `useLayoutEffect`, not `useEffect`, so the panel never
  // paints for even one frame at a stale/default position.
  useLayoutEffect(() => {
    if (!isOpen) return
    const rect = buttonRef.current?.getBoundingClientRect()
    if (!rect) return
    const left = Math.min(rect.left, window.innerWidth - PANEL_MAX_WIDTH - VIEWPORT_MARGIN)
    setPosition({ top: rect.bottom + 4, left: Math.max(VIEWPORT_MARGIN, left) })
  }, [isOpen])

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

    // Scrolling the message thread while the panel is open would leave
    // a portalled, `position: fixed` panel visually detached from the
    // button it belongs to (it doesn't scroll with the thread anymore,
    // unlike before the portal) -- closing on any scroll is simpler and
    // less surprising than repositioning it mid-scroll. `capture: true`
    // catches the scroll regardless of which ancestor is the actual
    // scrolling element (the chat thread's own `overflow-y-auto`
    // container, not `window`). The panel's own citation list is itself
    // scrollable (long source lists), so a scroll that originates inside
    // the panel must be excluded here -- otherwise scrolling the list
    // closes the panel it's inside of.
    function handleScroll(event) {
      if (panelRef.current?.contains(event.target)) return
      setIsOpen(false)
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('scroll', handleScroll, true)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('scroll', handleScroll, true)
    }
  }, [isOpen])

  function handleKeyDown(event) {
    if (event.key !== 'Escape') return
    event.stopPropagation()
    setIsOpen(false)
    buttonRef.current?.focus()
  }

  if (citations.length === 0) return null

  return (
    <div className="relative block w-fit" onKeyDown={handleKeyDown}>
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

      {isOpen &&
        position &&
        createPortal(
          <div
            ref={panelRef}
            role="group"
            aria-label={t('chat.sources.panelAria')}
            onKeyDown={handleKeyDown}
            style={{ top: position.top, left: position.left, maxWidth: PANEL_MAX_WIDTH }}
            className="fixed z-50 min-w-[220px] rounded-lg border border-border bg-card-bg py-2 text-[13.5px] shadow-modal"
          >
            <ul className="m-0 max-h-[168px] list-none space-y-1.5 overflow-y-auto p-0 px-3">
              {citations.map((citation, index) => (
                <li key={index}>
                  <CitationChip chapter={citation.chapter} documentFilename={citation.documentFilename} />
                </li>
              ))}
            </ul>
          </div>,
          document.body,
        )}
    </div>
  )
}
