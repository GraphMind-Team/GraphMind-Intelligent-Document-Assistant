// Shared stroke-icon frame -- one size, one stroke weight, one join style
// for every glyph that uses it, so document actions (DocumentCard's "⋮"
// menu, DocumentDetailPage's own button row) read as the same visual
// system as Shell's nav rail rather than each screen improvising its own
// icon language. `className` overrides the default size (Shell's rail
// glyphs are 18px; a denser menu item or an inline button icon commonly
// wants smaller); `strokeWidth` defaults to the same 1.7 every icon uses,
// overridable for the rare glyph (a small checkmark badge, say) that
// needs a bolder line to stay legible at a smaller size.
export default function Icon({ children, className = 'h-[18px] w-[18px]', strokeWidth = '1.7' }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={`shrink-0 ${className}`}
    >
      {children}
    </svg>
  )
}
