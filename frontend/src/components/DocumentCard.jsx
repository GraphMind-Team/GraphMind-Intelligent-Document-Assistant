import { Link } from 'react-router-dom'
import StatusPill from './StatusPill'
import { formatFileTypeShort, formatUploadedDate } from '../utils/documentFormat'

// One document as a card in the library grid (Story 2.2, human-requested
// design change from the mockup's `.doclist` table -- see the spec's
// Change Log).
//
// Carries exactly the same five facts the table columns did: file type
// (the icon tile), title, status, uploaded date, and the trash action.
//
// The file-icon tile reuses DESIGN.md's `.file-icon` treatment
// (`--citation` fill, `--primary` text) rather than inventing a colour:
// that is the one use of the citation token DESIGN.md sanctions outside a
// literal citation chip ("the file-type icon tile in upload rows"), so the
// grid stays inside the existing palette instead of adding to it.
export default function DocumentCard({ document, onCardClick }) {
  const detailHref = `/documents/${document.id}`

  return (
    // Click-anywhere is a mouse-convenience layer over the real <Link>
    // below -- the same split the table row used. The card is not itself a
    // link/button because the trash control lives inside it, and a
    // <button> nested in an <a> is invalid HTML that breaks keyboard and
    // screen-reader behavior. Keyboard users reach the document through
    // the title link and the trash through its own button, which is why
    // this carries no tabIndex or role.
    //
    // The handler sits on the <li> itself rather than an inner wrapper so
    // the clickable region is exactly the visible card -- with a wrapper,
    // a click landing on the <li>'s own box (outside the child) would do
    // nothing, since events bubble up rather than down.
    <li
      onClick={(event) => onCardClick(event, document.id)}
      className="flex cursor-pointer flex-col gap-3 rounded-lg border border-border bg-card-bg p-4 hover:border-accent"
    >
        <div className="flex items-start justify-between gap-2">
          <span
            aria-hidden="true"
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-citation text-[11px] font-extrabold tracking-[0.02em] text-primary"
          >
            {formatFileTypeShort(document.file_type)}
          </span>

          {/* Renders and is keyboard-focusable, but has no delete behavior
              wired -- that is Story 2.7. Not disabled: the story requires
              it stay reachable by Tab. stopPropagation is belt-and-braces
              alongside the card handler's own `closest('a, button')`
              guard; either alone would keep it from navigating. */}
          <button
            type="button"
            aria-label={`Delete ${document.filename}`}
            onClick={(event) => event.stopPropagation()}
            className="-mr-1 -mt-1 shrink-0 rounded-sm p-1 text-text2 hover:bg-surface2 hover:text-danger"
          >
            <svg
              aria-hidden="true"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-4 w-4"
            >
              <path d="M3 6h18" />
              <path d="M8 6V4h8v2" />
              <path d="M6 6l1 14h10l1-14" />
              <path d="M10 11v6M14 11v6" />
            </svg>
          </button>
        </div>

        {/* `break-words` rather than truncate: filenames are the one thing
            a user scans this grid for, and a silently clipped name is
            worse than a taller card. `line-clamp-2` bounds it so one
            pathological name can't stretch its whole grid row. */}
        <Link
          to={detailHref}
          className="line-clamp-2 text-sm font-semibold break-words text-text hover:underline"
        >
          {document.filename}
        </Link>

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
          <StatusPill status={document.status} />
          <span className="text-xs text-text2">{formatUploadedDate(document.created_at)}</span>
        </div>
    </li>
  )
}
