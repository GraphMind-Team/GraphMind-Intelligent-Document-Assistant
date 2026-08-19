import { useMemo, useState } from 'react'
import { badgeFor, paletteFor, relationshipLabelFor, typeColorFor } from './graphTheme'

// The accessible equivalent Story 4.1 (AC7/UX-DR28) requires: the canvas
// (GraphCanvas.jsx) has all pointer interaction disabled, so nothing on
// it reveals detail on hover -- this is the always-visible way to read
// every entity and relationship the canvas shows sighted users.
//
// Design system v2 rebuilds it as an *explorer* rather than a nested
// bullet dump. What changed and why:
//   - Entities render as cards in a responsive grid (type badge, name,
//     connection count) instead of indented <li> text, so the list is
//     scannable at a glance and each entity has a real hit area's worth
//     of visual weight.
//   - A search field and per-type filter chips sit above it. The canvas
//     is deliberately non-interactive, which left *no* way to find one
//     entity in a 150-node graph; this is that way, and it costs nothing
//     but local state.
//   - Relationships render as source -> chip -> target rows on their own
//     surface, so a relationship reads as a sentence.
//
// What deliberately did NOT change: this stays inside a `<details open>`
// labelled "View as list" (collapsible for a large graph, open by default
// so nobody has to click to read a handful of names), every entity and
// relationship stays in the DOM regardless of any filter's visual state,
// and the read-only/count sentence stays exactly as plain as it was.
//
// Filtering note: the search and type filters drive what is *rendered*,
// and an empty result renders an explicit "no matches" line rather than
// silence. The unfiltered totals stay visible in the count sentence
// above, so a filtered view can never be mistaken for the whole graph.
//
// Imports its color vocabulary from `graphTheme.js` -- the same module
// GraphCanvas.jsx draws the canvas from -- so a type's swatch and a
// relationship's label read identically in either view.
//
// `theme` is a prop, not its own `useTheme()` read -- GraphCanvas.jsx (the
// only caller) already resolves it once from `ThemeContext` and passes it
// down, the same way it passes `nodes`/`edges`.
export default function GraphSummary({ nodes, edges, theme }) {
  const palette = paletteFor(theme)
  const [query, setQuery] = useState('')
  const [activeType, setActiveType] = useState(null)

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

  const needle = query.trim().toLowerCase()

  // A group survives the type filter as a whole; individual entities are
  // then matched against the search text. A group whose entities all
  // filter out drops from the render entirely rather than leaving an
  // empty heading behind.
  const visibleGroups = useMemo(() => {
    return groups
      .filter(([type]) => !activeType || type === activeType)
      .map(([type, typeNodes]) => [
        type,
        needle ? typeNodes.filter((node) => node.name.toLowerCase().includes(needle)) : typeNodes,
      ])
      .filter(([, typeNodes]) => typeNodes.length > 0)
  }, [groups, activeType, needle])

  // An edge matches if either endpoint does -- searching "Maria" should
  // surface what Maria is connected to, not just the entity card.
  const visibleEdges = useMemo(() => {
    return edges.filter((edge) => {
      const source = nameById.get(edge.source) ?? edge.source
      const target = nameById.get(edge.target) ?? edge.target
      const matchesQuery =
        !needle ||
        source.toLowerCase().includes(needle) ||
        target.toLowerCase().includes(needle) ||
        relationshipLabelFor(edge.type).toLowerCase().includes(needle)
      if (!matchesQuery) return false
      if (!activeType) return true
      const endpointTypes = nodes
        .filter((node) => node.id === edge.source || node.id === edge.target)
        .map((node) => node.type)
      return endpointTypes.includes(activeType)
    })
  }, [edges, nameById, needle, activeType, nodes])

  const isFiltering = Boolean(needle || activeType)
  const hasNoMatches = isFiltering && visibleGroups.length === 0 && visibleEdges.length === 0

  const chipStyle = {
    backgroundColor: palette.chipBg,
    border: `1px solid ${palette.chipBorder}`,
    color: palette.accentText,
  }

  return (
    <div className="mt-5 text-sm">
      <p style={{ color: palette.ink2 }}>
        Read-only — hover, click and drag are disabled; the canvas can be zoomed and panned.{' '}
        {nodes.length} {nodes.length === 1 ? 'entity' : 'entities'}, {edges.length}{' '}
        {edges.length === 1 ? 'relationship' : 'relationships'} shown.
      </p>

      <details className="mt-3 group" open>
        <summary
          className="inline-flex cursor-pointer list-none items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-bold uppercase tracking-wide"
          style={chipStyle}
        >
          {/* A plain triangle glyph rather than the browser's default
              `<summary>` marker, whose rotation-on-open styling is
              inconsistent across engines -- rotated via a class toggle
              driven by the parent <details>'s own [open] state (no JS). */}
          <span aria-hidden="true" className="transition-transform group-open:rotate-90">
            ▸
          </span>
          View as list
        </summary>

        {/* ---- Filter bar ---- */}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <label htmlFor="graph-entity-search" className="sr-only">
            Search entities and relationships
          </label>
          <input
            id="graph-entity-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search entities…"
            className="min-w-0 flex-1 rounded-full px-4 py-2 text-[13px] sm:max-w-[280px] sm:flex-none"
            style={{
              backgroundColor: palette.cardBg,
              border: `1px solid ${palette.chipBorder}`,
              color: palette.ink,
            }}
          />

          {/* Type filters. Each chip's label is one string ("Person · 2")
              rather than a separate element per part, so a type name here
              can never be confused with the same type's group heading
              below. `aria-pressed` carries the toggle state, and the
              active chip is also filled, not tinted -- two cues. */}
          {groups.map(([type, typeNodes]) => {
            const typeColor = typeColorFor(theme, type)
            const isActive = activeType === type
            return (
              <button
                key={type}
                type="button"
                aria-pressed={isActive}
                onClick={() => setActiveType(isActive ? null : type)}
                className="rounded-full px-3 py-1.5 text-[12px] font-semibold"
                style={
                  isActive
                    ? { backgroundColor: typeColor.fill, color: typeColor.text, border: '1px solid transparent' }
                    : { ...chipStyle, color: palette.ink }
                }
              >
                {type} · {typeNodes.length}
              </button>
            )
          })}

          {isFiltering && (
            <button
              type="button"
              onClick={() => {
                setQuery('')
                setActiveType(null)
              }}
              className="rounded-full px-3 py-1.5 text-[12px] font-semibold underline"
              style={{ color: palette.accentText }}
            >
              Clear
            </button>
          )}
        </div>

        {hasNoMatches && (
          <p className="mt-4" style={{ color: palette.ink }}>
            Nothing matches that search.
          </p>
        )}

        {/* ---- Entities ---- */}
        <ul className="mt-4 flex list-none flex-col gap-5 p-0">
          {visibleGroups.map(([type, typeNodes]) => {
            const typeColor = typeColorFor(theme, type)
            return (
              <li key={type}>
                <div className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="inline-flex h-5 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                    style={{ backgroundColor: typeColor.fill, color: typeColor.text }}
                  >
                    {badgeFor(type)}
                  </span>
                  <span className="font-semibold" style={{ color: palette.ink }}>
                    {type}
                  </span>
                  <span className="text-[12px]" style={{ color: palette.accentText }}>
                    {typeNodes.length}
                  </span>
                </div>

                <ul className="mt-2.5 grid list-none grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-2 p-0">
                  {typeNodes.map((node) => (
                    <li
                      key={node.id}
                      className="flex items-center gap-2.5 rounded-xl px-3 py-2.5"
                      style={{
                        backgroundColor: palette.cardBg,
                        border: `1px solid ${palette.chipBorder}`,
                        color: palette.ink,
                      }}
                    >
                      {/* A dot in the type's own colour, so a card can be
                          traced back to its node on the canvas without
                          re-reading the heading above it. */}
                      <span
                        aria-hidden="true"
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: typeColor.fill }}
                      />
                      <span className="min-w-0 flex-1 truncate font-medium">{node.name}</span>
                      {/* `degree` is the same number that sizes the node
                          on the canvas -- stated here rather than left as
                          a size the reader has to eyeball. */}
                      {typeof node.degree === 'number' && (
                        <span className="shrink-0 text-[11px]" style={{ color: palette.accentText }}>
                          {node.degree}
                          <span className="sr-only">
                            {' '}
                            {node.degree === 1 ? 'connection' : 'connections'}
                          </span>
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </li>
            )
          })}
        </ul>

        {/* ---- Relationships ---- */}
        {edges.length > 0 && (
          <div className="mt-6">
            <span className="font-semibold" style={{ color: palette.ink }}>
              Relationships
            </span>
            <ul className="mt-2.5 flex list-none flex-col gap-2 p-0">
              {visibleEdges.map((edge, index) => (
                <li
                  key={`${edge.source}|${edge.type}|${edge.target}|${index}`}
                  className="flex flex-wrap items-center gap-2 rounded-xl px-3 py-2.5"
                  style={{
                    backgroundColor: palette.cardBg,
                    border: `1px solid ${palette.chipBorder}`,
                    color: palette.ink,
                  }}
                >
                  <span className="font-medium">{nameById.get(edge.source) ?? edge.source}</span>
                  <span
                    className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
                    style={chipStyle}
                  >
                    {relationshipLabelFor(edge.type)}
                  </span>
                  {/* Direction is meaningful (a Person works at an
                      Organization, not the reverse) -- the canvas draws an
                      arrowhead for it, and this is that arrowhead's
                      textual equivalent. */}
                  <span aria-hidden="true" style={{ color: palette.accentText }}>
                    →
                  </span>
                  <span className="font-medium">{nameById.get(edge.target) ?? edge.target}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </details>
    </div>
  )
}
