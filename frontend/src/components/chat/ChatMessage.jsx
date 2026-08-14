import CitationChip from './CitationChip'

// Plain, temporary copy -- placeholder pending Story 3.2's actual UX-DR15
// refusal design (which owns wording/visual treatment for "no supporting
// evidence"). This story only needs the two empty_reason outcomes to exist
// and be distinguishable from each other and from a real answer, not to be
// the final refusal UX.
const NOTICE_COPY = {
  no_documents: 'No documents are available to search yet.',
  no_answer: 'GraphMind could not generate an answer for this question.',
}

// Falls back rather than rendering `undefined` if the backend ever adds a
// new empty_reason (e.g. Story 3.2's refusal) before this map is updated to
// match -- an outdated frontend build should degrade to generic copy, not a
// blank notice bubble.
const DEFAULT_NOTICE_COPY = 'GraphMind has nothing to show for this question.'

// One message bubble (Story 3.1, UX-DR5): user messages are right-aligned
// with the primary fill and a sharp trailing corner; assistant messages are
// left-aligned with the surface fill and a sharp leading corner -- the one
// asymmetric (2px) corner is the sender cue, everything else is parallel.
//
// A `notice` message (empty_reason) is deliberately NOT bubble-shaped (no
// bg-surface/border/corner treatment) so it can never be mistaken for
// either a grounded answer or Story 3.2's future refusal bubble, both of
// which will be real bubbles.
export default function ChatMessage({ message }) {
  if (message.role === 'user') {
    return (
      <div className="ml-auto max-w-[70%] self-end rounded-[12px_12px_2px_12px] bg-primary px-3.5 py-2.5 text-[13.5px] text-on-primary">
        {/* Sighted users get the sender cue from alignment/fill/corner
            (UX-DR5) alone; a screen reader gets none of that, so without
            this prefix two turns read as one undifferentiated stream. */}
        <span className="sr-only">You: </span>
        {message.text}
      </div>
    )
  }

  if (message.role === 'notice') {
    return (
      <p className="mx-auto max-w-[78%] self-center text-center text-[13px] text-text2">
        {NOTICE_COPY[message.reason] ?? DEFAULT_NOTICE_COPY}
      </p>
    )
  }

  if (message.role === 'thinking') {
    return (
      <div className="mr-auto max-w-[78%] self-start rounded-[12px_12px_12px_2px] border border-border bg-surface px-3.5 py-3 text-[13.5px] text-text2">
        Thinking…
      </div>
    )
  }

  // 'assistant'
  return (
    <div className="mr-auto max-w-[78%] self-start rounded-[12px_12px_12px_2px] border border-border bg-surface px-3.5 py-3 text-[13.5px] leading-[1.55] text-text">
      <span className="sr-only">GraphMind: </span>
      {message.segments.map((segment, index) => (
        <span key={index}>
          {segment.text}
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
