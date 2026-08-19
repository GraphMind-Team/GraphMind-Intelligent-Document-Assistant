import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import GraphSummary from './GraphSummary'

const NODES = [
  { id: 'Person:Maria', name: 'Maria Ivanova', type: 'Person', degree: 2 },
  { id: 'Organization:TechCorp', name: 'TechCorp', type: 'Organization', degree: 1 },
  { id: 'Person:Ivan', name: 'Ivan Petrov', type: 'Person', degree: 0 },
]
const EDGES = [{ source: 'Person:Maria', target: 'Organization:TechCorp', type: 'WORKS_AT' }]

describe('GraphSummary', () => {
  it('states plainly that the graph is read-only, while the viewport itself can be zoomed/panned (AC7)', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    expect(screen.getByText(/read-only/i)).toBeInTheDocument()
    expect(screen.getByText(/hover, click and drag are disabled/i)).toBeInTheDocument()
    expect(screen.getByText(/zoomed and panned/i)).toBeInTheDocument()
  })

  it('reports the entity and relationship counts', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    expect(screen.getByText(/3 entities/)).toBeInTheDocument()
    expect(screen.getByText(/1 relationship\b/)).toBeInTheDocument()
  })

  it('groups entities by type, present in the DOM regardless of the details toggle (AC7)', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    // Not hover-gated: a keyboard/screen-reader user reaches every entity
    // here without any interaction at all -- <details> only affects
    // sighted visual collapse, never removes the content from the DOM.
    const personGroup = screen.getByText('Person').closest('li')
    expect(personGroup).toHaveTextContent('Maria Ivanova')
    expect(personGroup).toHaveTextContent('Ivan Petrov')
    const orgGroup = screen.getByText('Organization').closest('li')
    expect(orgGroup).toHaveTextContent('TechCorp')
  })

  it('the "View as list" toggle is keyboard-focusable, and starts open (AC1)', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    const toggle = screen.getByText('View as list')
    toggle.focus()
    expect(toggle).toHaveFocus()
    expect(toggle.closest('details')).toHaveAttribute('open')
  })

  it('lists each relationship with its type, using entity names rather than raw ids', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    const relationshipsGroup = screen.getByText('Relationships').closest('div')
    expect(relationshipsGroup).toHaveTextContent('Maria Ivanova')
    // Plain-language, not the raw enum value -- matches the canvas's own
    // relationship labels (graphTheme.js's `relationshipLabelFor`), so
    // switching between the canvas and this list reads as one system.
    expect(relationshipsGroup).toHaveTextContent('Works at')
    expect(relationshipsGroup).not.toHaveTextContent('WORKS_AT')
    expect(relationshipsGroup).toHaveTextContent('TechCorp')
  })

  it('filters entities and relationships by the search field (design system v2)', async () => {
    const user = userEvent.setup()
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    await user.type(screen.getByLabelText(/search entities/i), 'ivan')

    // "Maria Ivanova" and "Ivan Petrov" both contain "ivan"; TechCorp
    // does not, and its now-empty Organization group drops out entirely
    // rather than leaving a heading with nothing under it.
    // Maria appears twice -- once as an entity card, once as the source
    // of the surviving relationship row.
    expect(screen.getAllByText('Maria Ivanova').length).toBeGreaterThan(0)
    expect(screen.getByText('Ivan Petrov')).toBeInTheDocument()
    expect(screen.queryByText('Organization')).not.toBeInTheDocument()
  })

  it('narrows to one entity type when its filter chip is pressed, and restores on a second press', async () => {
    const user = userEvent.setup()
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    const chip = screen.getByRole('button', { name: /^Organization/ })
    await user.click(chip)

    expect(chip).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getAllByText('TechCorp').length).toBeGreaterThan(0)
    expect(screen.queryByText('Ivan Petrov')).not.toBeInTheDocument()

    await user.click(chip)

    expect(chip).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('Ivan Petrov')).toBeInTheDocument()
  })

  it('says so plainly when a search matches nothing, rather than rendering an empty list', async () => {
    const user = userEvent.setup()
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    await user.type(screen.getByLabelText(/search entities/i), 'zzzz')

    expect(screen.getByText(/nothing matches that search/i)).toBeInTheDocument()
    // The unfiltered totals stay on screen, so a filtered view can never
    // be mistaken for the whole graph being empty.
    expect(screen.getByText(/3 entities/)).toBeInTheDocument()
  })

  it('keeps relationships in their own disclosure, collapsed by default but still in the DOM', async () => {
    const user = userEvent.setup()
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    const toggle = screen.getByText('Relationships')
    const disclosure = toggle.closest('details')
    expect(disclosure).not.toHaveAttribute('open')
    // Collapsed is a visual state only -- <details> never removes its
    // content, so this stays reachable for assistive tech (AC7).
    expect(disclosure).toHaveTextContent('Works at')

    await user.click(toggle)

    expect(disclosure).toHaveAttribute('open')
  })

  it('handles an empty graph without crashing', () => {
    render(<GraphSummary nodes={[]} edges={[]} />)

    expect(screen.getByText(/0 entities, 0 relationships/)).toBeInTheDocument()
  })
})
