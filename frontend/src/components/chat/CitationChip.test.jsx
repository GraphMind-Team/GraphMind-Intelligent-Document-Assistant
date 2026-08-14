import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import CitationChip from './CitationChip'

describe('CitationChip', () => {
  it('renders the exact "Ch. {chapter}, {document_filename}" text', () => {
    render(<CitationChip chapter="Chapter 4" documentFilename="Vendor_Agreement_2026.pdf" />)

    expect(screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()
  })

  it('is a real <cite> element, not a bare styled span (UX-DR3/UX-DR28)', () => {
    render(<CitationChip chapter="Chapter 1" documentFilename="doc.pdf" />)

    const chip = screen.getByText('Ch. Chapter 1, doc.pdf')
    expect(chip.tagName).toBe('CITE')
  })

  it('is non-interactive -- no click handler, role, or tabIndex (jump-to-source is out of v1 scope)', () => {
    render(<CitationChip chapter="Chapter 1" documentFilename="doc.pdf" />)

    const chip = screen.getByText('Ch. Chapter 1, doc.pdf')
    expect(chip).not.toHaveAttribute('role')
    expect(chip).not.toHaveAttribute('tabIndex')
    expect(chip).not.toHaveAttribute('onclick')
  })
})
