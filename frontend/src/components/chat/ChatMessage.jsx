import { forwardRef } from 'react'
import { useTranslation } from 'react-i18next'
import CitationSummary from './CitationSummary'
import MessageActions from './MessageActions'
import UserMessage from './UserMessage'
import highlightMatches from './highlightMatches'
import Icon from '../Icon'

// Story 3.3/FR-11: `empty_scope` is distinct from `no_documents` -- the
// library isn't empty, the documents currently in scope just have no
// matching content. The default notice copy (translation key
// `chat.message.defaultNotice`) below would otherwise cover this, but the
// user narrowed the scope themselves and deserves honest copy that says
// so, not the generic fallback.
const NOTICE_KEYS = {
  no_documents: 'chat.message.noDocuments',
  empty_scope: 'chat.message.emptyScope',
  no_answer: 'chat.message.noAnswer',
}

// One message bubble (Story 3.1, UX-DR5): user messages are right-aligned
// with the primary fill and a sharp trailing corner; assistant messages are
// left-aligned with the surface fill and a sharp leading corner -- the one
// asymmetric (2px) corner is the sender cue, everything else is parallel.
//
// A `notice` message (empty_reason) is deliberately NOT bubble-shaped (no
// bg-surface/border/corner treatment) so it can never be mistaken for
// either a grounded answer or the refusal bubble below, both of which are
// real bubbles.
// `highlight` is the active chat-search query, already lowercased and
// trimmed by ChatPage ('' when the search is idle). Only the message's
// own words are marked -- the fixed notice/refusal copy below is
// GraphMind's wording, not something the user searched their own
// conversation for.
// `isActiveMatch` marks the one matching message the search's prev/next
// navigation currently points at (ChatPage tracks the ordinal, this
// component just renders the cue) -- a ring distinct from the `.chat-mark`
// wash so "which of the N matches am I looking at" is answerable without
// re-reading the "X of Y" count on every step. `outline`, not another
// `shadow-[...]`: every bubble already carries its own Tailwind-generated
// shadow utility (`shadow-card` / `shadow-[var(--glow)]`), and a second
// `box-shadow` utility doesn't compose with those -- Tailwind emits one
// `box-shadow` declaration per class and only one wins the cascade, so the
// ring silently lost to the bubble's own shadow. `outline` is a separate
// CSS property, so it always renders regardless of which shadow utility
// the bubble already has.
// Forwarded ref: ChatPage keeps one DOM node per message (keyed by its
// full-thread index) so the search nav can `scrollIntoView` a specific
// bubble -- every branch below attaches `ref` to its own root element for
// that reason.
const ChatMessage = forwardRef(function ChatMessage(
  { message, highlight = '', isActiveMatch = false, authFetch, onFollowupClick, onEditMessage },
  ref,
) {
  const { t } = useTranslation()
  const activeMatchClass = isActiveMatch ? ' outline outline-2 outline-accent outline-offset-2' : ''

  if (message.role === 'user') {
    return (
      <UserMessage
        ref={ref}
        id={message.id}
        text={message.text}
        highlight={highlight}
        isActiveMatch={isActiveMatch}
        onEditMessage={onEditMessage}
      />
    )
  }

  if (message.role === 'notice') {
    const noticeKey = NOTICE_KEYS[message.reason]
    return (
      <p ref={ref} className="anim-rise mx-auto max-w-[78%] self-center text-center text-[13px] text-text2">
        {noticeKey ? t(noticeKey) : t('chat.message.defaultNotice')}
      </p>
    )
  }

  // FR-10/UX-DR15: a designed refusal, not a failure and not an empty
  // answer -- must read as categorically different from both. Centered
  // with symmetric corners (no asymmetric leading/trailing corner), so it
  // sits outside UX-DR5's left/right turn-taking shape language entirely,
  // rather than looking like "GraphMind answered" in a different color.
  // The refusal token pair (not --surface/--text, the assistant bubble's
  // fill, and not --danger, reserved for real errors per AD-6 -- a
  // refusal is correct behavior, not a failure) plus the icon give it two
  // more differentiators than color alone -- deliberately not oversized
  // or shouting, though: a capped width (`max-w-[420px]`, not `78%` of
  // whatever wide the message pane happens to be) and body-text sizing,
  // since this reads as a plain, matter-of-fact statement, not an alert.
  // The sr-only "Refusal: " prefix mirrors the "You:"/"GraphMind:"
  // sender-cue mechanism below, so a screen reader hears a distinct
  // announcement, not merely a differently-styled one (UX-DR15/UX-DR24)
  // -- the same mechanism that already passed Story 3.1's own
  // accessibility review.
  if (message.role === 'refusal') {
    return (
      <div
        ref={ref}
        className="anim-rise mx-auto flex w-fit max-w-full items-center gap-2 self-center whitespace-nowrap rounded-full border border-border bg-refusal-bg px-3.5 py-2 text-[13px] text-refusal-text"
      >
        <Icon className="h-[15px] w-[15px] shrink-0">
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </Icon>
        <span className="sr-only">{t('chat.message.refusalPrefix')} </span>
        {t('chat.message.refusal')}
      </div>
    )
  }

  if (message.role === 'thinking') {
    return (
      <div
        ref={ref}
        className="anim-rise mr-auto flex max-w-[78%] items-center gap-2 self-start rounded-[20px_20px_20px_6px] border border-border bg-surface px-4 py-3 text-[14px] text-text2"
      >
        {/* Three staggered dots carry the "working" cue visually; the
            word stays in the DOM (sr-only) so the live region still
            announces something meaningful rather than nothing. */}
        <span className="sr-only">{t('chat.message.thinking')}</span>
        <span aria-hidden="true" className="flex items-center gap-1">
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className="anim-dot block h-1.5 w-1.5 rounded-full bg-accent"
              style={{ animationDelay: `${index * 0.16}s` }}
            />
          ))}
        </span>
        <span aria-hidden="true">{t('chat.message.thinking')}</span>
      </div>
    )
  }

  // 'assistant'. `bg-card-bg` is the base color; `--grad-brand-soft`
  // layers a faint brand-blue ombre over it (the same token `.btn-ghost`
  // uses), so the answer bubble reads as "GraphMind" at a glance without
  // needing a border-color trick.
  //
  // Citations used to render as a chip after every segment they belonged
  // to, which read as cluttered on a multi-segment answer. Deduped here
  // (by chapter+document, first-seen order) into one flat list and handed
  // to a single CitationSummary pill below the answer text instead --
  // "where did this come from" is now one click away rather than several
  // chips interrupting the prose.
  const seenCitations = new Set()
  const citations = []
  for (const segment of message.segments) {
    for (const citation of segment.citations) {
      const key = `${citation.chapter}::${citation.document_filename}`
      if (seenCitations.has(key)) continue
      seenCitations.add(key)
      citations.push({ chapter: citation.chapter, documentFilename: citation.document_filename })
    }
  }
  // Copy needs the answer's plain prose, citations stripped -- same
  // "citations aren't part of the answer's own text" treatment
  // `service.py::_pair_messages_into_turns`'s history-threading join
  // already gives this on the backend side.
  const answerText = message.segments.map((segment) => segment.text).join(' ')

  // The bubble (bordered/filled) holds only the answer's own text; the
  // sources pill + actions row sit below it as a separate row, outside
  // the bubble's border/background -- the ChatGPT/Claude convention,
  // rather than nested inside the bubble where they used to read as part
  // of the answer's own content.
  return (
    <div ref={ref} className="anim-rise mr-auto flex max-w-[78%] flex-col items-start gap-1.5 self-start">
      <div
        className={`rounded-[20px_20px_20px_6px] border border-border bg-card-bg bg-[image:var(--grad-brand-soft)] px-4 py-3 text-[14px] leading-[1.6] text-text shadow-card${activeMatchClass}`}
      >
        <span className="sr-only">{t('chat.message.assistantPrefix')} </span>
        {message.segments.map((segment, index) => (
          <span key={index}>{highlightMatches(segment.text, highlight)} </span>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 px-1">
        <CitationSummary citations={citations} />
        <MessageActions
          authFetch={authFetch}
          messageId={message.id}
          initialFeedback={message.feedback}
          answerText={answerText}
        />
      </div>
      {/* Model-suggested next questions (ChatGPT-style "Ask more:" chips) --
          only ever present on a message from a live turn's own AskResponse
          (chat/service.py never persists these, see AskResponse
          .followup_questions' own docstring), so a reloaded/older message
          simply has none and this renders nothing. Clicking a chip sends it
          immediately, the same "send, don't just fill the input" behavior
          the empty-thread welcome's own sample-question chips use. */}
      {message.followupQuestions?.length > 0 && (
        <div className="flex flex-col items-start gap-1.5 px-1">
          <p className="text-[11.5px] font-semibold text-text2">{t('chat.followup.label')}</p>
          <div className="flex flex-wrap gap-1.5">
            {message.followupQuestions.map((question) => (
              <button
                key={question}
                type="button"
                onClick={() => onFollowupClick(question)}
                className="rounded-full border border-border bg-surface2 px-3 py-1.5 text-[12.5px] text-text hover:border-accent hover:text-accent"
              >
                {question}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
})

export default ChatMessage
