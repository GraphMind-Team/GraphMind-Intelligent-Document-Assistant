import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../context/AuthContext'
import { getGraph } from '../api/graphClient'
import GraphCanvas from '../components/graph/GraphCanvas'

// Graph Preview (Story 4.1). A pure read: fetch -> loading/error/empty
// state -> render, mirroring DocumentsPage.jsx's fetch pattern.
//
// Design system v2 restructures the page around the canvas rather than
// around a tinted box. v1 put the page title, the copy, the notes and the
// canvas all inside one `--graph-card-bg` panel, which made the page's
// own heading look like part of the visualization and left the graph
// itself competing for space with prose. Now:
//   - The page header matches every other page in the app (eyebrow +
//     display title), sitting on the app's normal ground.
//   - Three stat tiles state what the graph actually contains, so the
//     size of it is a fact you can read rather than something you infer
//     from a picture.
//   - The canvas and its explorer live in one raised card below that, in
//     the graph feature's own surface tokens -- it keeps its identity as
//     its own "room" without swallowing the page chrome.
// Every `--graph-*` value is referenced through `var()` in a style or an
// arbitrary Tailwind value rather than a `useTheme()` read: those custom
// properties already swap per `[data-theme]` on their own, so this
// component never needs to know the theme (and its tests never need a
// ThemeProvider just to render it).

// One number plus its label. Deliberately not a generic <Card>: these
// three are the only tiles in the app, and inlining them here keeps the
// page readable as one file.
function StatTile({ label, value, hint }) {
  return (
    <div
      className="rounded-2xl px-5 py-4"
      style={{ backgroundColor: 'var(--graph-card-bg)', border: '1px solid var(--graph-card-border)' }}
    >
      <p
        className="font-display text-[26px] font-bold leading-none"
        style={{ color: 'var(--graph-ink)' }}
      >
        {value}
      </p>
      <p className="mt-1.5 text-[12px] font-semibold" style={{ color: 'var(--graph-accent-text)' }}>
        {label}
      </p>
      {hint && (
        <p className="mt-0.5 text-[12px]" style={{ color: 'var(--graph-ink2)' }}>
          {hint}
        </p>
      )}
    </div>
  )
}

export default function GraphPage() {
  const { t } = useTranslation()
  const { authFetch } = useAuth()
  const [graph, setGraph] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchGraph = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const data = await getGraph(authFetch)
      setGraph(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    fetchGraph()
  }, [fetchGraph])

  const hasEntities = Boolean(graph && graph.nodes.length > 0)
  // Story 4.1's node cap (`GRAPH_NODE_LIMIT` in neo4j_client.py): the
  // backend can return fewer entities than the account actually has.
  const isCapped = Boolean(graph && graph.total_node_count > graph.nodes.length)
  const typeCount = hasEntities ? new Set(graph.nodes.map((node) => node.type)).size : 0

  return (
    <>
      <header className="mb-6">
        <p className="text-eyebrow uppercase" style={{ color: 'var(--graph-accent-text)' }}>
          {t('graph.eyebrow')}
        </p>
        <h1 className="text-page-title text-text">{t('graph.title')}</h1>
        <p className="mt-1 max-w-[62ch] text-sm text-text2">
          {t('graph.subtitle')}
        </p>
      </header>

      {error && (
        <div
          role="alert"
          className="mb-5 flex flex-wrap items-center gap-3 rounded-2xl border border-danger/30 bg-danger/5 px-5 py-4"
        >
          <p className="text-sm text-danger">{error}</p>
          <button
            type="button"
            onClick={fetchGraph}
            className="btn-ghost shrink-0 rounded-full px-4 py-1.5 text-xs font-semibold"
          >
            {t('graph.retry')}
          </button>
        </div>
      )}

      {!error && isLoading && (
        // Skeleton rather than a bare "Loading graph..." line: the canvas
        // is a 520px block, and collapsing the page to one sentence and
        // back is a bigger visual jolt than holding its shape. The text
        // stays in the DOM for assistive tech (and for the page's tests),
        // it just sits inside the placeholder now.
        <div
          className="animate-pulse rounded-2xl"
          style={{
            height: 520,
            backgroundColor: 'var(--graph-card-bg)',
            border: '1px solid var(--graph-card-border)',
          }}
        >
          <p className="p-5 text-sm" style={{ color: 'var(--graph-ink2)' }}>
            {t('graph.loading')}
          </p>
        </div>
      )}

      {/* AC8: a plain-language message, not a blank canvas, for an account
          with no documents yet or none that produced entities -- the
          backend can't distinguish those two cases from an empty result
          alone, and there's no reason for this copy to either. */}
      {!error && !isLoading && graph && !hasEntities && (
        <div
          className="rounded-2xl px-6 py-12 text-center"
          style={{ backgroundColor: 'var(--graph-card-bg)', border: '1px solid var(--graph-card-border)' }}
        >
          {/* Three unconnected dots -- the graph's own shape, before
              anything has been connected. */}
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            fill="none"
            stroke="var(--graph-accent)"
            strokeWidth="1.4"
            className="mx-auto mb-4 h-10 w-10 opacity-70"
          >
            <circle cx="6" cy="7" r="2.4" />
            <circle cx="18" cy="9" r="2.4" />
            <circle cx="11" cy="18" r="2.4" />
          </svg>
          <p className="mx-auto max-w-[46ch] text-sm" style={{ color: 'var(--graph-ink2)' }}>
            {t('graph.emptyState')}
          </p>
        </div>
      )}

      {!error && !isLoading && graph && hasEntities && (
        <>
          <div className="mb-5 grid gap-4 sm:grid-cols-3">
            <StatTile
              label={t('graph.stats.entities')}
              value={graph.nodes.length}
              hint={isCapped ? t('graph.stats.ofTotal', { total: graph.total_node_count }) : undefined}
            />
            <StatTile label={t('graph.stats.relationships')} value={graph.edges.length} />
            <StatTile label={t('graph.stats.entityTypes')} value={typeCount} />
          </div>

          {isCapped && (
            <p className="mb-4 text-sm" style={{ color: 'var(--graph-ink2)' }}>
              {t('graph.cappedNote', { shown: graph.nodes.length, total: graph.total_node_count })}
            </p>
          )}

          <div
            className="rounded-2xl p-4 md:p-5"
            style={{
              backgroundColor: 'var(--graph-card-bg)',
              border: '1px solid var(--graph-card-border)',
            }}
          >
            <GraphCanvas graph={graph} />
          </div>
        </>
      )}
    </>
  )
}
