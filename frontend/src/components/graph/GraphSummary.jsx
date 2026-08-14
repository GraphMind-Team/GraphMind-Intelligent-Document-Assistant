import { useMemo } from 'react'

// The accessible equivalent Story 4.1 (AC7/UX-DR28) requires: the canvas
// (GraphCanvas.jsx) has all pointer interaction disabled, so nothing on
// it reveals detail on hover -- this is the always-visible, keyboard-
// reachable way to see every entity the canvas shows sighted users,
// grouped by type. It never hides behind a hover; `<details>` collapses
// its content visually by default but keeps it discoverable to assistive
// tech and keyboard users (Tab -> Enter/Space to expand), not a second
// hover-gated surface repeating the canvas's own limitation.
export default function GraphSummary({ nodes, edges }) {
  const groups = useMemo(() => {
    const byType = new Map()
    for (const node of nodes) {
      const list = byType.get(node.type) ?? []
      list.push(node)
      byType.set(node.type, list)
    }
    return [...byType.entries()].sort(([a], [b]) => a.localeCompare(b))
  }, [nodes])

  return (
    <div className="mt-3 text-sm text-text2">
      <p>
        Read-only — hover and click are disabled. {nodes.length}{' '}
        {nodes.length === 1 ? 'entity' : 'entities'}, {edges.length}{' '}
        {edges.length === 1 ? 'relationship' : 'relationships'} shown.
      </p>
      <details className="mt-2">
        <summary className="cursor-pointer text-text">View as list</summary>
        <ul className="mt-2 flex list-none flex-col gap-2 p-0">
          {groups.map(([type, typeNodes]) => (
            <li key={type}>
              <span className="font-semibold text-text">{type}</span>
              <ul className="ml-4 list-disc">
                {typeNodes.map((node) => (
                  <li key={node.id}>{node.name}</li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </details>
    </div>
  )
}
