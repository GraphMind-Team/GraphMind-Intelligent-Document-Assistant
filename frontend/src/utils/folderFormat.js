// Shared folder-color vocabulary and presentation helpers (folder-grouping
// feature). Mirrors `StatusPill.jsx`'s `STATUS_CLASSES`/`DOCUMENT_STATUSES`
// pattern: the enforced vocabulary lives here as a plain exported array,
// and each key maps to a `--folder-color-*` pastel token pair from
// `index.css` (light value in `:root`, dark override in
// `:root[data-theme="dark"]`, following the `--status-*` two-tone formula).
//
// Kept in sync by hand with `backend/app/folders/service.py`'s
// `FOLDER_COLORS` -- no shared codegen between the two languages here,
// same as `documentsClient.js`'s `ALLOWED_EXTENSIONS` mirrors
// `documents/service.py`'s own extension map.
export const FOLDER_COLORS = ['rose', 'peach', 'sun', 'mint', 'sky', 'lilac']

const FOLDER_COLOR_BG_CLASSES = {
  rose: 'bg-folder-color-rose-bg',
  peach: 'bg-folder-color-peach-bg',
  sun: 'bg-folder-color-sun-bg',
  mint: 'bg-folder-color-mint-bg',
  sky: 'bg-folder-color-sky-bg',
  lilac: 'bg-folder-color-lilac-bg',
}

const FOLDER_COLOR_TEXT_CLASSES = {
  rose: 'text-folder-color-rose-text',
  peach: 'text-folder-color-peach-text',
  sun: 'text-folder-color-sun-text',
  mint: 'text-folder-color-mint-text',
  sky: 'text-folder-color-sky-text',
  lilac: 'text-folder-color-lilac-text',
}

// Neutral fallback for a color outside the vocabulary (backend/frontend
// drift) -- still renders, rather than silently breaking the tile.
const UNKNOWN_COLOR_BG_CLASS = 'bg-surface'
const UNKNOWN_COLOR_TEXT_CLASS = 'text-text'

// Used by FolderModal's color picker, which keeps its own circular swatch
// convention for choosing a color (a `role="radio"` dot per option) --
// unrelated to how a folder's color renders on its own tile.
export function folderSwatchClass(color) {
  return FOLDER_COLOR_BG_CLASSES[color] ?? UNKNOWN_COLOR_BG_CLASS
}

// The folder tile's own fill: the whole tile is tinted with the folder's
// color (bg + matching readable text), the same two-tone formula
// StatusPill's STATUS_CLASSES already uses, rather than a small color dot.
export function folderTileClasses(color) {
  return {
    bg: FOLDER_COLOR_BG_CLASSES[color] ?? UNKNOWN_COLOR_BG_CLASS,
    text: FOLDER_COLOR_TEXT_CLASSES[color] ?? UNKNOWN_COLOR_TEXT_CLASS,
  }
}
