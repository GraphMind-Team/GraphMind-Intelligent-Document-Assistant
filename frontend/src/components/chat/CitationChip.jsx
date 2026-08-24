// Citation chip (Story 3.1, UX-DR3/UX-DR28): a real `<cite>` element, not a
// bare styled `<span>`, so a screen-reader user encounters it as
// programmatically distinct from ordinary answer text. Text content is
// exactly `Ch. {chapter}, {document_filename}` -- no extra punctuation, no
// prefix. Non-interactive by simply not adding interaction (no onClick, no
// role="button", no tabIndex) -- jump-to-source is explicitly out of v1
// scope.
//
// No font-size of its own: the chip inherits its container's, so it never
// drifts out of sync with a bubble/panel size change elsewhere. `w-fit
// max-w-full` + `break-words` (rather than the `whitespace-nowrap` this
// used to carry from its old inline-after-a-sentence days) lets a long
// filename wrap onto a second line inside CitationSummary's fixed-width
// panel instead of overflowing past the panel's rounded edge.
import { useTranslation } from 'react-i18next'

export default function CitationChip({ chapter, documentFilename }) {
  const { t } = useTranslation()
  return (
    <cite className="not-italic block w-fit max-w-full break-words rounded-[6px] bg-citation px-2 py-1 font-bold text-citation-text">
      {t('chat.citationPrefix')} {chapter}, {documentFilename}
    </cite>
  )
}
