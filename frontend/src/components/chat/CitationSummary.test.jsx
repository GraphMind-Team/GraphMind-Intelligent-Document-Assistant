import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import CitationSummary from './CitationSummary'

const ONE_CITATION = [{ chapter: 'Chapter 4', documentFilename: 'Vendor_Agreement_2026.pdf' }]
const TWO_CITATIONS = [
  { chapter: 'Chapter 4', documentFilename: 'Vendor_Agreement_2026.pdf' },
  { chapter: 'Chapter 1', documentFilename: 'Onboarding_Guide.pdf' },
]

describe('CitationSummary', () => {
  it('renders nothing for an empty citations list', () => {
    const { container } = render(<CitationSummary citations={[]} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders one toggle pill with the citation count, panel collapsed by default', () => {
    render(<CitationSummary citations={TWO_CITATIONS} />)

    const toggle = screen.getByRole('button', { name: '2 sources' })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).not.toBeInTheDocument()
  })

  it('pluralizes the toggle label for a single citation', () => {
    render(<CitationSummary citations={ONE_CITATION} />)
    expect(screen.getByRole('button', { name: '1 source' })).toBeInTheDocument()
  })

  it('opens the panel on click, revealing every citation as a real <cite> chip', async () => {
    const user = userEvent.setup()
    render(<CitationSummary citations={TWO_CITATIONS} />)

    await user.click(screen.getByRole('button', { name: '2 sources' }))

    const first = screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')
    const second = screen.getByText('Ch. Chapter 1, Onboarding_Guide.pdf')
    expect(first.tagName).toBe('CITE')
    expect(second.tagName).toBe('CITE')
    expect(screen.getByRole('button', { name: '2 sources' })).toHaveAttribute('aria-expanded', 'true')
  })

  it('closes on a second click of the toggle', async () => {
    const user = userEvent.setup()
    render(<CitationSummary citations={ONE_CITATION} />)

    const toggle = screen.getByRole('button', { name: '1 source' })
    await user.click(toggle)
    expect(screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()

    await user.click(toggle)
    expect(screen.queryByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).not.toBeInTheDocument()
  })

  it('closes on Escape and returns focus to the toggle', async () => {
    const user = userEvent.setup()
    render(<CitationSummary citations={ONE_CITATION} />)

    const toggle = screen.getByRole('button', { name: '1 source' })
    await user.click(toggle)
    expect(screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()

    await user.keyboard('{Escape}')
    expect(screen.queryByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).not.toBeInTheDocument()
    expect(toggle).toHaveFocus()
  })

  it('closes on an outside click', async () => {
    const user = userEvent.setup()
    render(
      <div>
        <button type="button">outside</button>
        <CitationSummary citations={ONE_CITATION} />
      </div>,
    )

    await user.click(screen.getByRole('button', { name: '1 source' }))
    expect(screen.getByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'outside' }))
    expect(screen.queryByText('Ch. Chapter 4, Vendor_Agreement_2026.pdf')).not.toBeInTheDocument()
  })
})
