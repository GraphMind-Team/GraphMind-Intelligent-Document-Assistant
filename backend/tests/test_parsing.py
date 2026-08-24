"""Unit tests for `app.documents.parsing` -- format-specific parsing bugs
that don't need the full upload/ingest flow to reproduce or pin down.
"""

import io

import pytest
from docx import Document as DocxDocument
from pptx import Presentation

from app.documents import parsing
from app.documents.parsing import UnparseableDocument, parse_document


def _docx_bytes(build) -> bytes:
    document = DocxDocument()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _pptx_bytes(build) -> bytes:
    presentation = Presentation()
    build(presentation)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()

_MINIMAL_PDF_WITH_PREAMBLE = b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R /Outlines 6 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R 7 0 R] /Count 2 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 200 200] /Contents 5 0 R >>endobj
4 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
5 0 obj<< /Length 50 >>
stream
BT /F1 12 Tf 10 100 Td (Title page preamble text) Tj ET
endstream
endobj
6 0 obj<< /Type /Outlines /First 8 0 R /Last 8 0 R /Count 1 >>endobj
7 0 obj<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> /MediaBox [0 0 200 200] /Contents 9 0 R >>endobj
8 0 obj<< /Title (Chapter One) /Parent 6 0 R /Dest [7 0 R /Fit] >>endobj
9 0 obj<< /Length 40 >>
stream
BT /F1 12 Tf 10 100 Td (Chapter one body) Tj ET
endstream
endobj
xref
0 10
trailer<< /Size 10 /Root 1 0 R >>
startxref
0
%%EOF"""


def test_markdown_preserves_text_before_first_heading():
    chunks = parse_document(
        "markdown", b"Intro paragraph that matters.\n\n# Chapter One\n\nBody here."
    )

    assert any("Intro paragraph that matters." in c.text for c in chunks)
    preamble_chunk = next(c for c in chunks if "Intro paragraph that matters." in c.text)
    assert preamble_chunk.chapter == "Full Document"
    assert preamble_chunk.chunk_index == 0

    chapter_one_chunk = next(c for c in chunks if c.chapter == "Chapter One")
    assert "Body here." in chapter_one_chunk.text


def test_markdown_with_no_preamble_has_no_spurious_full_document_chapter():
    chunks = parse_document("markdown", b"# Chapter One\n\nBody here.")

    assert {c.chapter for c in chunks} == {"Chapter One"}


def test_pdf_outline_preserves_pages_before_first_bookmark():
    chunks = parse_document("pdf", _MINIMAL_PDF_WITH_PREAMBLE)

    preamble_chunk = next(c for c in chunks if "Title page preamble text" in c.text)
    assert preamble_chunk.chapter == "Full Document"
    assert preamble_chunk.chunk_index == 0

    chapter_chunk = next(c for c in chunks if c.chapter == "Chapter One")
    assert "Chapter one body" in chapter_chunk.text
    assert chapter_chunk.chunk_index == 1


def test_html_comments_are_excluded_from_passage_text():
    chunks = parse_document(
        "html",
        b"<html><body><!-- secret internal note --><h1>T</h1><p>Body</p></body></html>",
    )

    assert len(chunks) == 1
    assert chunks[0].chapter == "T"
    assert chunks[0].text == "Body"
    assert "secret internal note" not in chunks[0].text


def test_html_comment_before_first_heading_does_not_leak_into_preamble():
    chunks = parse_document(
        "html",
        b"<html><body><!-- internal note -->Real preamble text<h1>T</h1><p>Body</p></body></html>",
    )

    all_text = " ".join(c.text for c in chunks)
    assert "internal note" not in all_text
    assert "Real preamble text" in all_text


def test_chunk_word_count_stays_within_the_embedding_model_s_token_budget():
    # Sized against shared/embeddings/model.py's 512-token multilingual
    # limit -- not re-asserting the exact constant, but that whatever it
    # is stays comfortably under a budget that would otherwise mean most
    # of a chunk's stored, citable text was never actually embedded.
    text = " ".join(f"word{i}" for i in range(1000))
    chunks = parse_document("markdown", text.encode())

    for chunk in chunks:
        assert len(chunk.text.split()) <= parsing._CHUNK_WORD_COUNT


def test_markdown_heading_inside_a_code_fence_is_not_treated_as_a_chapter():
    md = (
        b"# Real Heading\n\n"
        b"Some intro text.\n\n"
        b"```bash\n# install deps\npip install foo\n```\n\n"
        b"## Another Real Heading\n\nFinal text."
    )

    chunks = parse_document("markdown", md)

    chapters = {c.chapter for c in chunks}
    assert chapters == {"Real Heading", "Another Real Heading"}
    assert "install deps" not in chapters


# ---------------------------------------------------------------------------
# DOCX / PPTX.
# ---------------------------------------------------------------------------


def test_docx_headings_become_chapters():
    def build(document):
        document.add_paragraph("Intro before any heading.")
        document.add_heading("Chapter One", level=1)
        document.add_paragraph("Body of chapter one.")
        document.add_heading("Chapter Two", level=2)
        document.add_paragraph("Body of chapter two.")

    chunks = parse_document("docx", _docx_bytes(build))

    assert {c.chapter for c in chunks} == {"Full Document", "Chapter One", "Chapter Two"}
    chapter_one_chunk = next(c for c in chunks if c.chapter == "Chapter One")
    assert "Body of chapter one." in chapter_one_chunk.text
    chapter_two_chunk = next(c for c in chunks if c.chapter == "Chapter Two")
    assert "Body of chapter two." in chapter_two_chunk.text


def test_docx_with_no_headings_has_single_full_document_chapter():
    def build(document):
        document.add_paragraph("Just a plain paragraph.")

    chunks = parse_document("docx", _docx_bytes(build))

    assert {c.chapter for c in chunks} == {"Full Document"}


def test_docx_unparseable_bytes_raise():
    with pytest.raises(UnparseableDocument):
        parse_document("docx", b"not a real docx file")


def test_pptx_slide_title_becomes_chapter_and_is_not_duplicated_into_body():
    def build(presentation):
        slide = presentation.slides.add_slide(presentation.slide_layouts[0])
        slide.shapes.title.text = "Welcome Slide"
        slide.placeholders[1].text = "Subtitle body text."

    chunks = parse_document("pptx", _pptx_bytes(build))

    assert {c.chapter for c in chunks} == {"Welcome Slide"}
    assert any("Subtitle body text." in c.text for c in chunks)
    assert not any("Welcome Slide" in c.text for c in chunks)


def test_pptx_slide_without_title_gets_generated_chapter_name():
    def build(presentation):
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        textbox = slide.shapes.add_textbox(0, 0, 100, 100)
        textbox.text_frame.text = "Body text with no title placeholder."

    chunks = parse_document("pptx", _pptx_bytes(build))

    assert {c.chapter for c in chunks} == {"Slide 1"}
    assert any("Body text with no title placeholder." in c.text for c in chunks)


def test_pptx_unparseable_bytes_raise():
    with pytest.raises(UnparseableDocument):
        parse_document("pptx", b"not a real pptx file")


# ---------------------------------------------------------------------------
# Glyph-spaced PDF repair. Some PDFs (design-tool exports especially)
# position every character individually, so pypdf faithfully returns
# "К о н т а к т и" for "Контакти". Observed on two real CV PDFs where
# 100% of extracted tokens were single characters.
# ---------------------------------------------------------------------------

from app.documents.parsing import _looks_char_spaced, _repair_char_spacing


def test_char_spacing_detected_on_fully_glyph_spaced_text():
    text = "К о н т а к т и\n0 8 8 6 9 9 7 8 5 8\nТ е л е ф о н\ny o a n a s b @ g m a i l . c o m"
    assert _looks_char_spaced(text)


def test_normal_prose_is_not_detected_as_char_spaced():
    """The detector must not fire on real documents -- repairing one would
    glue every word to its neighbour."""
    text = (
        "Project Aurora is GraphMind's internal codename for the Q3 2026 "
        "knowledge-graph visualization redesign. The project began on "
        "2026-04-01 and is scheduled to ship on 2026-09-15. Elena Rusev "
        "leads it, and Northwind Robotics supplies the hardware."
    )
    assert not _looks_char_spaced(text)


def test_bulgarian_prose_is_not_detected_as_char_spaced():
    """Cyrillic is the script the failing PDFs were in -- the detector must
    key on token length, not on the alphabet."""
    text = (
        "Личен дневник по разработката на Gamification модула върху "
        "стажантската среда на Sirma Academy LMS. Всеки запис отговаря на "
        "commit — какво е добавено и защо, подредено хронологично."
    )
    assert not _looks_char_spaced(text)


def test_short_text_is_never_treated_as_char_spaced():
    """Below the token floor the ratio is meaningless -- a two-token page
    would otherwise score 100% and be 'repaired' into nonsense."""
    assert not _looks_char_spaced("A B")
    assert not _looks_char_spaced("")


def test_repair_rejoins_words_using_the_double_space_boundary():
    """Single space separates glyphs; two or more marks a real word
    boundary. That distinction is what makes this reconstruction lossless
    rather than a guess."""
    assert _repair_char_spacing("г р а д  К ю с т е н д и л") == "град Кюстендил"
    assert _repair_char_spacing("Y O A N A  B O R I S O V A") == "YOANA BORISOVA"


def test_repair_preserves_line_structure():
    """Chapter-heading detection downstream still reads these lines, so
    the line count must not change."""
    repaired = _repair_char_spacing("К о н т а к т и\n0 8 8 6 9 9 7 8 5 8")
    assert repaired == "Контакти\n0886997858"


def test_repair_keeps_punctuation_inside_a_rejoined_token():
    assert _repair_char_spacing("y o a n a s b @ g m a i l . c o m") == "yoanasb@gmail.com"


def test_repaired_pdf_text_is_substantially_shorter():
    """The repair roughly halves the character count, which is why it also
    matters for cost: extraction text is capped at EXTRACTION_CHAR_BUDGET,
    so glyph spacing was spending half that budget on spaces."""
    spaced = "\n".join(["К о н т а к т и  Т е л е ф о н"] * 10)
    assert len(_repair_char_spacing(spaced)) < len(spaced) / 1.8
