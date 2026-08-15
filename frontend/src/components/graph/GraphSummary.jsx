import { useMemo } from 'react'

// The accessible equivalent Story 4.1 (AC7/UX-DR28) requires: the canvas
// (GraphCanvas.jsx) has all pointer interaction disabled, so nothing on
// it reveals detail on hover -- this is the always-visible way to see
// every entity and relationship the canvas shows sighted users, grouped
// by type. `<details open>` -- not plain markup -- so the content is
// still a `<details>` element a user can collapse if their graph grows
// large, but it renders open by default (today's lists are small, a
// handful of entities per account) rather than making the user click
// "View as list" just to read a single name.
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

  const nameById = useMemo(() => new Map(nodes.map((node) => [node.id, node.name])), [nodes])

  return (
    <div className="mt-3 text-sm text-text2">
      <p>
        Read-only — hover, click and drag are disabled; the canvas can be zoomed and panned.{' '}
        {nodes.length} {nodes.length === 1 ? 'entity' : 'entities'}, {edges.length}{' '}
        {edges.length === 1 ? 'relationship' : 'relationships'} shown.
      </p>
      <details className="mt-2" open>
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
        {edges.length > 0 && (
          <div className="mt-3">
            <span className="font-semibold text-text">Relationships</span>
            <ul className="ml-4 list-disc">
              {edges.map((edge, index) => (
                <li key={`${edge.source}|${edge.type}|${edge.target}|${index}`}>
                  {nameById.get(edge.source) ?? edge.source}{' '}
                  <span className="font-semibold text-text">{edge.type}</span>{' '}
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
