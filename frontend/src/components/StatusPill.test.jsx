import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StatusPill, { DOCUMENT_STATUSES } from './StatusPill'

describe('StatusPill', () => {
  it('exposes the FR-4 five-status vocabulary in pipeline order', () => {
    expect(DOCUMENT_STATUSES).toEqual(['Uploaded', 'Extracting', 'Graphing', 'Ready', 'Failed'])
  })

  // The visible label is a human-readable translation, not necessarily the
  // backend's own status word (e.g. `Extracting` reads as "Reading
  // document") -- this map is what the label is expected to say for each
  // status, independent of the raw key `DOCUMENT_STATUSES` carries.
  const STATUS_LABELS = {
    Uploaded: 'Uploaded',
    Extracting: 'Reading document',
    Graphing: 'Finding connections',
    Ready: 'Ready',
    Failed: 'Failed',
  }

  it.each(DOCUMENT_STATUSES)(
    'renders %s as real text paired with its own token pair, never colour alone',
    (status) => {
      const { container } = render(<StatusPill status={status} />)
      const label = STATUS_LABELS[status]

      // Real, selectable DOM text -- not a pseudo-element, icon glyph, or
      // an aria-label standing in for a visible label (UX-DR4/UX-DR28).
      const pill = screen.getByText(label)
      expect(pill).toBeInTheDocument()
      expect(pill).not.toHaveAttribute('aria-label')
      expect(container.textContent).toBe(label)

      // Each state carries a distinct tint + text token pair from Story 1.2
      // -- keyed on the backend status word, not the (possibly different)
      // visible label.
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
