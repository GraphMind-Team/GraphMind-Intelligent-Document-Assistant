// Splits a run of message text around every case-insensitive occurrence
// of the chat-search query and wraps the hits in <mark> (styled by
// .chat-mark in index.css). Returns the plain string when there is
// nothing to mark, so an inactive search adds no wrapper elements to
// the thread at all.
//
// Deliberately a string scan, not a RegExp: the query is raw user input,
// so a regex would need escaping anyway, and `indexOf` can't be tripped
// by a stray `(` or `*` in the first place.
export default function highlightMatches(text, needle) {
  const source = text ?? ''
  if (!needle) return source

  const haystack = source.toLowerCase()
  const parts = []
  let cursor = 0

  for (;;) {
    const hit = haystack.indexOf(needle, cursor)
    if (hit === -1) break
    if (hit > cursor) parts.push(source.slice(cursor, hit))
    parts.push(
      <mark key={hit} className="chat-mark">
        {source.slice(hit, hit + needle.length)}
      </mark>,
    )
    cursor = hit + needle.length
  }

  if (parts.length === 0) return source
  if (cursor < source.length) parts.push(source.slice(cursor))
  return parts
}
