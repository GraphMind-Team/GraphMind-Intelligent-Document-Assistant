import JSZip from 'jszip'
import { describe, expect, it } from 'vitest'
import { extractPptxSlides } from './pptxOutline'

const A_NS = 'http://schemas.openxmlformats.org/drawingml/2006/main'
const P_NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
const R_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
const PKG_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
const SLIDE_REL_TYPE = `${R_NS}/slide`

function slideXml(lines) {
  const paragraphs = lines.map((line) => `<a:p><a:r><a:t>${line}</a:t></a:r></a:p>`).join('')
  return (
    `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
    `<p:sld xmlns:a="${A_NS}" xmlns:p="${P_NS}">` +
    `<p:cSld><p:spTree><p:sp><p:txBody>${paragraphs}</p:txBody></p:sp></p:spTree></p:cSld>` +
    `</p:sld>`
  )
}

// `slidesByFileNumber` keys are the `slideN.xml` numbers (the part names
// PowerPoint assigns at creation time and never renumbers); `displayOrder`
// lists those same numbers in the order the deck actually presents them.
// Omitting `displayOrder` writes no presentation.xml at all, which is how
// the fallback path gets exercised.
async function buildPptx(slidesByFileNumber, displayOrder) {
  const zip = new JSZip()
  Object.entries(slidesByFileNumber).forEach(([number, lines]) => {
    zip.file(`ppt/slides/slide${number}.xml`, slideXml(lines))
  })

  if (displayOrder) {
    const relationships = displayOrder
      .map(
        (number) =>
          `<Relationship Id="rId${number}" Type="${SLIDE_REL_TYPE}" Target="slides/slide${number}.xml"/>`,
      )
      .join('')
    zip.file(
      'ppt/_rels/presentation.xml.rels',
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<Relationships xmlns="${PKG_REL_NS}">${relationships}</Relationships>`,
    )
    const slideIds = displayOrder
      .map((number, index) => `<p:sldId id="${256 + index}" r:id="rId${number}"/>`)
      .join('')
    zip.file(
      'ppt/presentation.xml',
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>` +
        `<p:presentation xmlns:p="${P_NS}" xmlns:r="${R_NS}">` +
        `<p:sldIdLst>${slideIds}</p:sldIdLst></p:presentation>`,
    )
  }

  return zip.generateAsync({ type: 'arraybuffer' })
}

describe('extractPptxSlides', () => {
  it('numbers slides by their position in the deck, not by part name', async () => {
    // A deck whose third-created slide was dragged to the front -- the part
    // names stay slide1/2/3, so file-name ordering would report "Closing"
    // as slide 3 while every backend citation calls it slide 1.
    const buffer = await buildPptx(
      { 1: ['Middle'], 2: ['Last'], 3: ['Closing moved to front'] },
      [3, 1, 2],
    )

    const slides = await extractPptxSlides(buffer)

    expect(slides).toEqual([
      { number: 1, lines: ['Closing moved to front'] },
      { number: 2, lines: ['Middle'] },
      { number: 3, lines: ['Last'] },
    ])
  })

  it('falls back to part-name order when there is no presentation part', async () => {
    // slide10 sorts before slide2 lexicographically, so the fallback has to
    // sort on the parsed number rather than on the raw archive path.
    const buffer = await buildPptx({ 1: ['One'], 2: ['Two'], 10: ['Ten'] })

    const slides = await extractPptxSlides(buffer)

    expect(slides.map((slide) => slide.lines[0])).toEqual(['One', 'Two', 'Ten'])
    expect(slides.map((slide) => slide.number)).toEqual([1, 2, 3])
  })

  it('falls back rather than dropping a slide the relationship chain cannot resolve', async () => {
    // A dangling r:id would otherwise renumber everything after it -- the
    // exact mismatch display ordering exists to prevent.
    const buffer = await buildPptx({ 1: ['One'], 2: ['Two'] }, [1, 2])
    const zip = await JSZip.loadAsync(buffer)
    zip.remove('ppt/_rels/presentation.xml.rels')
    zip.file(
      'ppt/_rels/presentation.xml.rels',
      `<Relationships xmlns="${PKG_REL_NS}">` +
        `<Relationship Id="rId1" Type="${SLIDE_REL_TYPE}" Target="slides/slide1.xml"/>` +
        `</Relationships>`,
    )

    const slides = await extractPptxSlides(await zip.generateAsync({ type: 'arraybuffer' }))

    expect(slides.map((slide) => slide.lines[0])).toEqual(['One', 'Two'])
  })

  it('resolves package-absolute relationship targets', async () => {
    const buffer = await buildPptx({ 1: ['Only slide'] }, [1])
    const zip = await JSZip.loadAsync(buffer)
    zip.file(
      'ppt/_rels/presentation.xml.rels',
      `<Relationships xmlns="${PKG_REL_NS}">` +
        `<Relationship Id="rId1" Type="${SLIDE_REL_TYPE}" Target="/ppt/slides/slide1.xml"/>` +
        `</Relationships>`,
    )

    const slides = await extractPptxSlides(await zip.generateAsync({ type: 'arraybuffer' }))

    expect(slides).toEqual([{ number: 1, lines: ['Only slide'] }])
  })

  it('reports a slide with no text runs as an empty line list', async () => {
    const buffer = await buildPptx({ 1: ['Title'], 2: [] }, [1, 2])

    const slides = await extractPptxSlides(buffer)

    expect(slides[1]).toEqual({ number: 2, lines: [] })
  })

  it('rejects when the file is not a zip at all', async () => {
    const buffer = new TextEncoder().encode('not actually a zip').buffer

    await expect(extractPptxSlides(buffer)).rejects.toThrow()
  })
})
