import CitationChip from './CitationChip'
import highlightMatches from './highlightMatches'

const NOTICE_COPY = {
  no_documents: 'No documents are available to search yet.',
  // Story 3.3/FR-11: distinct from no_documents -- the library isn't
  // empty, the documents currently in scope just have no matching
  // content. DEFAULT_NOTICE_COPY below would otherwise cover this, but
  // the user narrowed the scope themselves and deserves honest copy that
  // says so, not the generic fallback.
  empty_scope: 'No content found in the documents you selected.',
  no_answer: 'GraphMind could not generate an answer for this question.',
}

// Falls back rather than rendering `undefined` if the backend ever adds a
// new empty_reason before this map is updated to match -- an outdated
// frontend build should degrade to generic copy, not a blank notice bubble.
// (Story 3.2's refusal is not such a case: it has its own `role: 'refusal'`
// message, set in ChatPage.jsx, and never reaches this map.)
const DEFAULT_NOTICE_COPY = 'GraphMind has nothing to show for this question.'

// UX-DR19: plain, declarative, no apology/hedging/emoji. Fixed here rather
// than sourced from the backend, matching NOTICE_COPY's convention of
// keeping exact required wording in the frontend.
const REFUSAL_COPY = 'No supporting evidence found in your documents for this question.'

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
export default function ChatMessage({ message, highlight = '' }) {
  if (message.role === 'user') {
    return (
      <div className="anim-rise ml-auto max-w-[70%] self-end rounded-[20px_20px_6px_20px] bg-[image:var(--grad-brand)] px-4 py-2.5 text-[14px] text-white shadow-[var(--glow)]">
        {/* Sighted users get the sender cue from alignment/fill/corner
            (UX-DR5) alone; a screen reader gets none of that, so without
            this prefix two turns read as one undifferentiated stream. */}
        <span className="sr-only">You: </span>
        {highlightMatches(message.text, highlight)}
      </div>
    )
  }

  if (message.role === 'notice') {
    return (
      <p className="anim-rise mx-auto max-w-[78%] self-center text-center text-[13px] text-text2">
        {NOTICE_COPY[message.reason] ?? DEFAULT_NOTICE_COPY}
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
  // refusal is correct behavior, not a failure) plus font-medium give it
  // two more differentiators than color alone. The sr-only "Refusal: "
  // prefix mirrors the "You:"/"GraphMind:" sender-cue mechanism below, so
  // a screen reader hears a distinct announcement, not merely a
  // differently-styled one (UX-DR15/UX-DR24) -- the same mechanism that
  // already passed Story 3.1's own accessibility review.
  if (message.role === 'refusal') {
    return (
      <div className="anim-rise max-w-[78%] self-center rounded-2xl border border-warning/40 bg-refusal-bg px-4 py-3 text-center text-[14px] font-medium text-refusal-text">
        <span className="sr-only">Refusal: </span>
        {REFUSAL_COPY}
      </div>
    )
  }

  if (message.role === 'thinking') {
    return (
      <div className="anim-rise mr-auto flex max-w-[78%] items-center gap-2 self-start rounded-[20px_20px_20px_6px] border border-border bg-surface px-4 py-3 text-[14px] text-text2">
        {/* Three staggered dots carry the "working" cue visually; the
            word stays in the DOM (sr-only) so the live region still
            announces something meaningful rather than nothing. */}
        <span className="sr-only">Thinking…</span>
        <span aria-hidden="true" className="flex items-center gap-1">
          {[0, 1, 2].map((index) => (
            <span
              key={index}
              className="anim-dot block h-1.5 w-1.5 rounded-full bg-accent"
              style={{ animationDelay: `${index * 0.16}s` }}
            />
          ))}
        </span>
        <span aria-hidden="true">Thinking…</span>
      </div>
    )
  }

  // 'assistant'. `bg-card-bg` is the base color; `--grad-brand-soft`
  // layers a faint brand-blue ombre over it (the same token `.btn-ghost`
  // uses), so the answer bubble reads as "GraphMind" at a glance without
  // needing a border-color trick.
  return (
    <div className="anim-rise mr-auto max-w-[78%] self-start rounded-[20px_20px_20px_6px] border border-border bg-card-bg bg-[image:var(--grad-brand-soft)] px-4 py-3 text-[14px] leading-[1.6] text-text shadow-card">
      <span className="sr-only">GraphMind: </span>
      {message.segments.map((segment, index) => (
        <span key={index}>
          {highlightMatches(segment.text, highlight)}
          {segment.citations.map((citation, citationIndex) => (
            <CitationChip
              key={citationIndex}
              chapter={citation.chapter}
              documentFilename={citation.document_filename}
            />
          ))}{' '}
        </span>
      ))}
    </div>
  )
}
