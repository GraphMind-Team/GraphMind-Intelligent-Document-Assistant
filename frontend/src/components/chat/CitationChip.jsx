// Citation chip (Story 3.1, UX-DR3/UX-DR28): a real `<cite>` element, not a
// bare styled `<span>`, so a screen-reader user encounters it as
// programmatically distinct from ordinary answer text. Text content is
// exactly `Ch. {chapter}, {document_filename}` -- no extra punctuation, no
// prefix. Non-interactive by simply not adding interaction (no onClick, no
// role="button", no tabIndex) -- jump-to-source is explicitly out of v1
// scope.
//
// No font-size of its own: the chip inherits the answer bubble's, so a
// citation always reads at the same size as the sentence it belongs to.
// It used to set 11.5px and shrank to noticeably smaller than the answer
// text; pinning a literal here again would just let the two drift apart
// the next time the bubble's size moves. Weight and color still separate
// it from prose.
export default function CitationChip({ chapter, documentFilename }) {
  return (
    <cite className="not-italic inline-block rounded-[6px] bg-citation px-2 py-0.5 font-bold text-citation-text whitespace-nowrap ml-1">
      Ch. {chapter}, {documentFilename}
    </cite>
  )
}
