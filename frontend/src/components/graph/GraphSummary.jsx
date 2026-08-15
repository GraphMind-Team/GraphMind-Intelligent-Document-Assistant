import { useMemo } from 'react'
import { badgeFor, paletteFor, relationshipLabelFor, typeColorFor } from './graphTheme'

// The accessible equivalent Story 4.1 (AC7/UX-DR28) requires: the canvas
// (GraphCanvas.jsx) has all pointer interaction disabled, so nothing on
// it reveals detail on hover -- this is the always-visible way to see
// every entity and relationship the canvas shows sighted users, grouped
// by type. `<details open>` -- not plain markup -- so the content is
// still a `<details>` element a user can collapse if their graph grows
// large, but it renders open by default (today's lists are small, a
// handful of entities per account) rather than making the user click
// "View as list" just to read a single name.
//
// Imports its color vocabulary from `graphTheme.js` -- the same module
// GraphCanvas.jsx draws the canvas from -- so a type's swatch and a
// relationship's label read identically whether you're looking at the
// canvas or this list. Before this redesign the two views used unrelated
// styling (plain bullet lists here, colored badges on the canvas); this
// is the fix, not a new requirement invented for its own sake.
//
// `theme` is a prop, not its own `useTheme()` read -- GraphCanvas.jsx (the
// only caller) already resolves it once from `ThemeContext` and passes it
// down, the same way it already passes `nodes`/`edges`, rather than this
// component reaching into the same context a second time.
export default function GraphSummary({ nodes, edges, theme }) {
  const palette = paletteFor(theme)

  const groups = useMemo(() => {
    const byType = new Map()
    for (const node of nodes) {
      const list = byType.get(node.type) ?? []
      list.push(node)
      byType.set(node.type, list)
    }
    return [...byType.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [nodes])

  const nameById = useMemo(() => new Map(nodes.map((node) => [node.id, node.name])), [nodes])

  return (
    <div className="mt-4 text-sm">
      <p style={{ color: palette.ink2 }}>
        Read-only — hover, click and drag are disabled; the canvas can be zoomed and panned.{' '}
        {nodes.length} {nodes.length === 1 ? 'entity' : 'entities'}, {edges.length}{' '}
        {edges.length === 1 ? 'relationship' : 'relationships'} shown.
      </p>
      <details className="mt-2 group" open>
        <summary
          className="inline-flex cursor-pointer list-none items-center gap-1 rounded-full px-3 py-1 text-xs font-bold uppercase tracking-wide"
          style={{ backgroundColor: palette.chipBg, border: `1px solid ${palette.chipBorder}`, color: palette.accentText }}
        >
          {/* A plain triangle glyph rather than relying on the browser's
              default `<summary>` marker, whose rotation-on-open styling
              is inconsistent across engines -- rotated via a class toggle
              driven by the parent <details>'s own [open] state (no JS). */}
          <span aria-hidden="true" className="transition-transform group-open:rotate-90">
            ▸
          </span>
          View as list
        </summary>
        <ul className="mt-3 flex list-none flex-col gap-3 p-0">
          {groups.map(([type, typeNodes]) => {
            const typeColor = typeColorFor(theme, type)
            return (
              <li key={type}>
                <div className="flex items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="inline-flex h-5 w-7 items-center justify-center rounded-full text-[11px] font-bold shadow-sm"
                    style={{ backgroundColor: typeColor.fill, color: typeColor.text }}
                  >
                    {badgeFor(type)}
                  </span>
                  <span className="font-semibold" style={{ color: palette.ink }}>
                    {type}
                  </span>
                </div>
                <ul className="mt-1.5 ml-1 flex list-none flex-col gap-1 border-l pl-4" style={{ borderColor: palette.chipBorder }}>
                  {typeNodes.map((node) => (
                    <li key={node.id} style={{ color: palette.ink }}>
                      {node.name}
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ul>
        {edges.length > 0 && (
          <div className="mt-4">
            <span className="font-semibold" style={{ color: palette.ink }}>
              Relationships
            </span>
            <ul className="mt-1.5 ml-1 flex list-none flex-col gap-1.5 border-l pl-4" style={{ borderColor: palette.chipBorder }}>
              {edges.map((edge, index) => (
                <li key={`${edge.source}|${edge.type}|${edge.target}|${index}`} style={{ color: palette.ink }}>
                  {nameById.get(edge.source) ?? edge.source}{' '}
                  <span
                    className="mx-0.5 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold"
                    style={{ backgroundColor: palette.chipBg, border: `1px solid ${palette.chipBorder}`, color: palette.accentText }}
                  >
                    {relationshipLabelFor(edge.type)}
                  </span>{' '}
                  {nameById.get(edge.target) ?? edge.target}
                </li>
              ))}
            </ul>
          </div>
        )}
      </details>
    </div>
  )
}
