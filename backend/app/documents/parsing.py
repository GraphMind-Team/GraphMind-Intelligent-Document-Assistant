"""PDF/Markdown/HTML parsing and chunking (Story 2.3, FR-3).

Output is plain text only, all the way through -- extracted chapter
titles and body text are never rendered as HTML or Markdown anywhere
downstream (a standing constraint: a malicious `.md`/`.html` upload's
heading text must never reach a raw-HTML renderer, per
`_bmad-output/implementation-artifacts/deferred-work.md`).

Uploaded bytes are only extension/content-type-checked at upload time,
never magic-byte-verified (same doc) -- every parser here must catch its
own failure mode and raise `UnparseableDocument` rather than assume the
bytes are trustworthy for their claimed `file_type`.
"""

import io
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup, NavigableString
from pypdf import PdfReader

# ~400 words per chunk with a ~50-word overlap between consecutive chunks
# -- cheap, and avoids losing a passage that straddles a chunk boundary.
# chunk_index is sequential across the whole document, not reset per
# chapter.
_CHUNK_WORD_COUNT = 400
_CHUNK_OVERLAP_WORDS = 50

_FULL_DOCUMENT_CHAPTER = "Full Document"
_HEADING_TAGS = ("h1", "h2", "h3")

_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class ParsedChunk:
    chapter: str
    chunk_index: int
    text: str


class UnparseableDocument(Exception):
    """`content` couldn't be parsed as its claimed `file_type`, or yielded
    no extractable text. The expected outcome for a corrupt or mislabeled
    upload -- callers must catch this, not let it propagate."""


def parse_document(file_type: str, content: bytes) -> list[ParsedChunk]:
    """PDF/Markdown/HTML bytes -> chaptered, chunked plain-text passages.

    Raises `UnparseableDocument` if the bytes can't be parsed as
    `file_type`, or if parsing succeeds but yields zero extractable text
    (an empty file or a scanned/image-only PDF) -- AC1 requires "one or
    more passages", so a silent zero-passage success is treated as a
    failure, not success.
    """
    if file_type == "pdf":
        chapters = _parse_pdf(content)
    elif file_type == "markdown":
        chapters = _parse_markdown(content)
    elif file_type == "html":
        chapters = _parse_html(content)
    else:
        raise UnparseableDocument(f"Unsupported file_type: {file_type!r}")

    chunks = _chunk_chapters(chapters)
    if not chunks:
        raise UnparseableDocument("Document produced no extractable text.")
    return chunks


def _chunk_chapters(chapters: list[tuple[str, str]]) -> list[ParsedChunk]:
    chunks: list[ParsedChunk] = []
    chunk_index = 0
    for chapter, text in chapters:
        words = text.split()
        if not words:
            continue
        start = 0
        while start < len(words):
            end = start + _CHUNK_WORD_COUNT
            chunk_text = " ".join(words[start:end])
            chunks.append(ParsedChunk(chapter=chapter, chunk_index=chunk_index, text=chunk_text))
            chunk_index += 1
            if end >= len(words):
                break
            start = end - _CHUNK_OVERLAP_WORDS
    return chunks


# --- Markdown ---------------------------------------------------------


def _parse_markdown(content: bytes) -> list[tuple[str, str]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnparseableDocument("Could not decode Markdown as UTF-8.") from exc

    matches = list(_MARKDOWN_HEADING_RE.finditer(text))
    if not matches:
        return [(_FULL_DOCUMENT_CHAPTER, text)]

    chapters: list[tuple[str, str]] = []
    for i, match in enumerate(matches):
        title = match.group(1).strip() or _FULL_DOCUMENT_CHAPTER
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chapters.append((title, text[body_start:body_end].strip()))
    return chapters


# --- HTML ---------------------------------------------------------------


def _parse_html(content: bytes) -> list[tuple[str, str]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnparseableDocument("Could not decode HTML as UTF-8.") from exc

    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception as exc:  # pragma: no cover - html.parser rarely raises
        raise UnparseableDocument("Could not parse HTML.") from exc

    for tag in soup(["script", "style"]):
        tag.decompose()

    root = soup.body or soup

    chapters: list[tuple[str, list[str]]] = []
    current_title = _FULL_DOCUMENT_CHAPTER
    current_parts: list[str] = []

    for element in root.descendants:
        if getattr(element, "name", None) in _HEADING_TAGS:
            if current_parts:
                chapters.append((current_title, current_parts))
            current_title = element.get_text(strip=True) or _FULL_DOCUMENT_CHAPTER
            current_parts = []
        elif isinstance(element, NavigableString):
            # Skip the heading's own text node -- already captured as
            # current_title above, would otherwise duplicate into the body.
            if getattr(element.parent, "name", None) in _HEADING_TAGS:
                continue
            piece = str(element).strip()
            if piece:
                current_parts.append(piece)

    if current_parts:
        chapters.append((current_title, current_parts))

    return [(title, " ".join(parts)) for title, parts in chapters]


# --- PDF ------------------------------------------------------------------


def _parse_pdf(content: bytes) -> list[tuple[str, str]]:
    try:
        reader = PdfReader(io.BytesIO(content))
        page_texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise UnparseableDocument("Could not parse PDF.") from exc

    chapters = _pdf_chapters_from_outline(reader, page_texts)
    if chapters is not None:
        return chapters
    return [(_FULL_DOCUMENT_CHAPTER, "\n".join(page_texts))]


def _pdf_chapters_from_outline(
    reader: PdfReader, page_texts: list[str]
) -> list[tuple[str, str]] | None:
    """Top-level PDF bookmarks as chapters, or `None` to fall back to a
    single "Full Document" chapter.

    A strict, checkable condition rather than an open-ended "if it looks
    clean" judgment call: the outline must be a flat list (no nested
    sub-lists) and every entry must resolve to a page number with no
    exception. Any nesting, an empty outline, or any resolution failure
    falls back immediately -- no partial/best-effort read of a broken or
    deeply-nested table of contents.
    """
    try:
        outline = reader.outline
    except Exception:
        return None
    if not outline:
        return None
    if any(isinstance(item, list) for item in outline):
        return None

    entries: list[tuple[str, int]] = []
    try:
        for item in outline:
            page_number = reader.get_destination_page_number(item)
            if page_number is None:
                return None
            title = item.title or _FULL_DOCUMENT_CHAPTER
            entries.append((title, page_number))
    except Exception:
        return None

    entries.sort(key=lambda entry: entry[1])
    chapters: list[tuple[str, str]] = []
    for i, (title, start_page) in enumerate(entries):
        end_page = entries[i + 1][1] if i + 1 < len(entries) else len(page_texts)
        chapters.append((title, "\n".join(page_texts[start_page:end_page])))
    return chapters
