import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import GraphSummary from './GraphSummary'

const NODES = [
  { id: 'Person:Maria', name: 'Maria Ivanova', type: 'Person', degree: 2 },
  { id: 'Organization:TechCorp', name: 'TechCorp', type: 'Organization', degree: 1 },
  { id: 'Person:Ivan', name: 'Ivan Petrov', type: 'Person', degree: 0 },
]
const EDGES = [{ source: 'Person:Maria', target: 'Organization:TechCorp', type: 'WORKS_AT' }]

describe('GraphSummary', () => {
  it('states plainly that the view is read-only with no hover/click (AC7)', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    expect(screen.getByText(/read-only/i)).toBeInTheDocument()
    expect(screen.getByText(/hover and click are disabled/i)).toBeInTheDocument()
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

  it('the "View as list" toggle is keyboard-focusable', () => {
    render(<GraphSummary nodes={NODES} edges={EDGES} />)

    const toggle = screen.getByText('View as list')
    toggle.focus()
    expect(toggle).toHaveFocus()
  })

  it('handles an empty graph without crashing', () => {
    render(<GraphSummary nodes={[]} edges={[]} />)

    expect(screen.getByText(/0 entities, 0 relationships/)).toBeInTheDocument()
  })
})
