import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StatusPill, { DOCUMENT_STATUSES } from './StatusPill'

describe('StatusPill', () => {
  it('exposes the FR-4 five-status vocabulary in pipeline order', () => {
    expect(DOCUMENT_STATUSES).toEqual(['Uploaded', 'Extracting', 'Graphing', 'Ready', 'Failed'])
  })

  it.each(DOCUMENT_STATUSES)(
    'renders %s as real text paired with its own token pair, never colour alone',
    (status) => {
      const { container } = render(<StatusPill status={status} />)

      // Real, selectable DOM text -- not a pseudo-element, icon glyph, or
      // an aria-label standing in for a visible label (UX-DR4/UX-DR28).
      const pill = screen.getByText(status)
      expect(pill).toBeInTheDocument()
      expect(pill).not.toHaveAttribute('aria-label')
      expect(container.textContent).toBe(status)

      // Each state carries a distinct tint + text token pair from Story 1.2.
      const slug = status.toLowerCase()
      expect(pill).toHaveClass(`bg-status-${slug}-bg`)
      expect(pill).toHaveClass(`text-status-${slug}-text`)
    },
  )

  it('still shows the label for a status outside the vocabulary', () => {
    render(<StatusPill status="Quarantined" />)

    const pill = screen.getByText('Quarantined')
    expect(pill).toBeInTheDocument()
    expect(pill).toHaveClass('bg-surface')
  })

  it('renders nothing when there is no status', () => {
    const { container } = render(<StatusPill status="" />)
    expect(container).toBeEmptyDOMElement()
  })
})
