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

// Neutral fallback for a color outside the vocabulary (backend/frontend
// drift) -- still renders, rather than silently breaking the tile.
const UNKNOWN_COLOR_BG_CLASS = 'bg-surface'

// The swatch's own fill -- used for the small color dot on a folder tile
// and for each option in FolderModal's color picker. There is no
// filled-chip rendering of a folder's color anywhere in the app (unlike
// StatusPill's bg+text pairing), so there is no second bg+text helper here.
export function folderSwatchClass(color) {
  return FOLDER_COLOR_BG_CLASSES[color] ?? UNKNOWN_COLOR_BG_CLASS
}
