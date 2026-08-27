import JSZip from 'jszip'

// A deck's *display* order lives in `ppt/presentation.xml`'s `<p:sldIdLst>`,
// which references slide parts by relationship id -- resolved through
// `ppt/_rels/presentation.xml.rels`. It is NOT the `slideN.xml` numbering:
// PowerPoint never renumbers slide parts when you reorder a deck, so a
// slide dragged to the front keeps its original file name. Reading the
// relationship chain is what makes "Slide N" here mean the same thing it
// means in the backend, which walks `python-pptx`'s `presentation.slides`
// (also sldIdLst order) in `backend/app/documents/parsing.py`.
const PRESENTATION_PATH = 'ppt/presentation.xml'
const PRESENTATION_RELS_PATH = 'ppt/_rels/presentation.xml.rels'

// Fallback only, for a file whose relationship chain can't be resolved (see
// `readSlidePathsInDisplayOrder`). JSZip preserves the exact archive paths,
// and slide files aren't necessarily listed in numeric order
// (`slide10.xml` sorts before `slide2.xml` lexicographically), so the
// number is pulled out here and sorted on explicitly.
const SLIDE_PATH_PATTERN = /^ppt\/slides\/slide(\d+)\.xml$/

const PRESENTATIONML_NS = 'http://schemas.openxmlformats.org/presentationml/2006/main'
const OFFICE_REL_NS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
const PACKAGE_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

// DOMParser never throws on malformed XML -- it hands back a document whose
// root is `<parsererror>` instead -- so every parse goes through here and
// callers branch on null rather than silently walking an error document.
function parseXml(xml) {
  const doc = new DOMParser().parseFromString(xml, 'application/xml')
  return doc.getElementsByTagName('parsererror').length > 0 ? null : doc
}

function readEntry(zip, path) {
  const entry = zip.files[path]
  return entry ? entry.async('string') : Promise.resolve(null)
}

// Relationship targets are relative to the *owning part's* directory --
// `ppt/_rels/presentation.xml.rels` describes `ppt/presentation.xml`, so
// `slides/slide1.xml` means `ppt/slides/slide1.xml`. A leading slash makes
// the target package-absolute instead.
function resolvePresentationRelTarget(target) {
  if (target.startsWith('/')) return target.slice(1)
  const resolved = []
  for (const segment of `ppt/${target}`.split('/')) {
    if (segment === '' || segment === '.') continue
    if (segment === '..') resolved.pop()
    else resolved.push(segment)
  }
  return resolved.join('/')
}

// Returns slide part paths in display order, or null if any link in the
// chain is missing or unreadable. Null rather than a partial list on
// purpose: dropping a slide we couldn't resolve would renumber every slide
// after it, which is the exact failure this function exists to prevent.
async function readSlidePathsInDisplayOrder(zip) {
  const [presentationXml, relsXml] = await Promise.all([
    readEntry(zip, PRESENTATION_PATH),
    readEntry(zip, PRESENTATION_RELS_PATH),
  ])
  if (presentationXml === null || relsXml === null) return null

  const presentation = parseXml(presentationXml)
  const rels = parseXml(relsXml)
  if (!presentation || !rels) return null

  const targetsById = new Map(
    Array.from(rels.getElementsByTagNameNS(PACKAGE_REL_NS, 'Relationship')).map((rel) => [
      rel.getAttribute('Id'),
      rel.getAttribute('Target'),
    ]),
  )

  const slideIds = Array.from(presentation.getElementsByTagNameNS(PRESENTATIONML_NS, 'sldId'))
  if (slideIds.length === 0) return null

  const paths = []
  for (const slideId of slideIds) {
    const target = targetsById.get(slideId.getAttributeNS(OFFICE_REL_NS, 'id'))
    if (!target) return null
    const path = resolvePresentationRelTarget(target)
    if (!zip.files[path]) return null
    paths.push(path)
  }
  return paths
}

function slidePathsByFileNumber(zip) {
  return Object.keys(zip.files)
    .map((path) => {
      const match = path.match(SLIDE_PATH_PATTERN)
      return match ? { path, number: Number(match[1]) } : null
    })
    .filter((entry) => entry !== null)
    .sort((a, b) => a.number - b.number)
    .map((entry) => entry.path)
}

// Text runs live in `<a:t>` elements grouped under `<a:p>` paragraphs, per
// the OOXML DrawingML text-body schema `python-pptx` itself reads
// server-side (`backend/app/documents/parsing.py`) -- this mirrors that
// extraction in the browser rather than pulling in a second parsing
// library just to read the same XML shape.
function extractParagraphLines(slideXml) {
  const doc = parseXml(slideXml)
  if (!doc) return []
  const paragraphs = Array.from(doc.getElementsByTagName('a:p'))
  return paragraphs
    .map((paragraph) =>
      Array.from(paragraph.getElementsByTagName('a:t'))
        .map((node) => node.textContent)
        .join(''),
    )
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
}

// Reads a PPTX file's slide text client-side, for the preview modal's text
// outline (no client-side visual PPTX renderer is mature/secure enough to
// use here -- see PreviewModal.jsx's own note on that). `number` is the
// slide's position in the deck, counted from 1, matching how the backend
// numbers slides in citations.
export async function extractPptxSlides(arrayBuffer) {
  const zip = await JSZip.loadAsync(arrayBuffer)
  const slidePaths = (await readSlidePathsInDisplayOrder(zip)) ?? slidePathsByFileNumber(zip)

  return Promise.all(
    slidePaths.map(async (path, index) => {
      const xml = await zip.files[path].async('string')
      return { number: index + 1, lines: extractParagraphLines(xml) }
    }),
  )
}
