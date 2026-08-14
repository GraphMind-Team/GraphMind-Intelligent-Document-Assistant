// Citation chip (Story 3.1, UX-DR3/UX-DR28): a real `<cite>` element, not a
// bare styled `<span>`, so a screen-reader user encounters it as
// programmatically distinct from ordinary answer text. Text content is
// exactly `Ch. {chapter}, {document_filename}` -- no extra punctuation, no
// prefix. Non-interactive by simply not adding interaction (no onClick, no
// role="button", no tabIndex) -- jump-to-source is explicitly out of v1
// scope.
export default function CitationChip({ chapter, documentFilename }) {
  return (
    <cite className="not-italic inline-block rounded-[6px] bg-citation px-2 py-0.5 text-[11.5px] font-bold text-citation-text whitespace-nowrap ml-1">
      Ch. {chapter}, {documentFilename}
    </cite>
  )
}
