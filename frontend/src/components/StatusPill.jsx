// Shared ingestion-status pill (Story 2.2).
//
// Extracted rather than inlined in the Documents table because Epic 3's
// chat scope panel renders the same five states -- and because only 2 of
// the 5 token pairs were originally specified (epic-2-context.md's
// accessibility note), so one component is what makes the other three
// verifiable in a single place.
//
// UX-DR4/UX-DR28: the label is real, selectable DOM text paired with the
// tint -- never colour alone, never a pseudo-element, icon glyph, or an
// `aria-label`-only affordance. Do not "simplify" this into a
// `::before { content: ... }` or a title attribute; that reintroduces the
// exact failure mode the constraint exists to prevent.
//
// Token pairs come from Story 1.2 (`--status-*-bg` / `--status-*-text`,
// re-pointed into Tailwind's @theme in index.css), which owns their
// contrast verification in both themes.
const STATUS_CLASSES = {
  Uploaded: 'bg-status-uploaded-bg text-status-uploaded-text',
  Extracting: 'bg-status-extracting-bg text-status-extracting-text',
  Graphing: 'bg-status-graphing-bg text-status-graphing-text',
  Ready: 'bg-status-ready-bg text-status-ready-text',
  Failed: 'bg-status-failed-bg text-status-failed-text',
}

// The FR-4 five-value vocabulary, in pipeline order -- the same order the
// backend advances a document through. Exported so the Documents table's
// "Sort: Status" orders by that progression rather than alphabetically.
export const DOCUMENT_STATUSES = Object.keys(STATUS_CLASSES)

// Neutral surface for a status outside the vocabulary (backend drift).
// Still renders the label as text, so an unexpected value is visible
// rather than silently swallowed.
const UNKNOWN_STATUS_CLASSES = 'bg-surface text-text2'

export default function StatusPill({ status }) {
  if (!status) return null

  return (
    <span
      className={[
        'inline-block rounded-full px-2.5 py-[3px] text-[11px] font-bold',
        STATUS_CLASSES[status] ?? UNKNOWN_STATUS_CLASSES,
      ].join(' ')}
    >
      {status}
    </span>
  )
}
