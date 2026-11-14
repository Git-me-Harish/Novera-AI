"""Ingestion: every supported format, noise cleaning, safety checks and
structure-aware chunking. Fixtures are generated here, never committed."""
import re
import zipfile
from datetime import date

import fitz
import pytest

from app.core.config import settings
from app.services.document_processing import cleaning
from app.services.document_processing.chunker import SemanticChunker
from app.services.document_processing.elements import DocumentStructure, ExtractedElement, ExtractionError, heading
from app.services.document_processing.tables import split_markdown
from app.services.document_processing.text_extractor import text_extractor


def _types(structure):
    return [e.element_type for e in structure.elements]


def _norm(text):
    return re.sub(r"\W+", " ", text).lower().strip()


# ── PDF ───────────────────────────────────────────────────────────────────────

def _pdf(path, pages):
    doc = fitz.open()
    for number, lines in enumerate(pages, start=1):
        page = doc.new_page()
        y = 60
        for text, size, bold in lines:
            page.insert_text((60, y), text, fontsize=size, fontname="hebo" if bold else "helv")
            y += size * 1.8
        page.insert_text((60, 800), f"Acme Lending Manual   Page {number} of {len(pages)}", fontsize=8)
    doc.save(path)


def test_pdf_headings_from_typography_and_running_footers_removed(tmp_path):
    body = "Borrowers repay weekly at the centre meeting under joint liability terms."
    path = tmp_path / "manual.pdf"
    _pdf(path, [
        [("Collections", 16, True), (body, 10, False), ("Late payments", 12, True), (body, 10, False)],
        [("Collections", 16, True), (body, 10, False), ("Write-offs", 12, True), (body, 10, False)],
        [("Disbursement", 16, True), (body, 10, False)],
    ])
    structure = text_extractor.extract_document(path)
    headings = [(e.content, e.metadata["level"]) for e in structure.elements if e.element_type == "heading"]
    assert ("Collections", 1) in headings and ("Late payments", 2) in headings
    text = " ".join(e.content for e in structure.elements)
    assert "Acme Lending Manual" not in text  # running footer on every page
    assert structure.metadata["removed_running_lines"] >= 1
    assert all(e.page_number in (1, 2, 3) for e in structure.elements)


def test_pdf_ruled_table_is_read_as_a_table(tmp_path):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((60, 60), "Fee schedule for all loan products offered this year.", fontsize=10)
    cells = [["Product", "Fee"], ["Group loan", "1%"], ["Gold loan", "0.5%"]]
    x0, y0, w, h = 60, 100, 160, 24
    for r, row in enumerate(cells):
        for c, value in enumerate(row):
            rect = fitz.Rect(x0 + c * w, y0 + r * h, x0 + (c + 1) * w, y0 + (r + 1) * h)
            page.draw_rect(rect, color=(0, 0, 0), width=0.8)
            page.insert_text((rect.x0 + 4, rect.y0 + 16), value, fontsize=10)
    path = tmp_path / "fees.pdf"
    doc.save(path)
    structure = text_extractor.extract_document(path)
    tables = [e for e in structure.elements if e.element_type == "table"]
    assert len(tables) == 1 and tables[0].metadata["header"] == ["Product", "Fee"]
    assert ["Gold loan", "0.5%"] in tables[0].metadata["rows"]
    loose = " ".join(e.content for e in structure.elements if e.element_type != "table")
    assert "Gold loan" not in loose  # table text is not duplicated as paragraphs


def test_scanned_pdf_without_ocr_is_refused_clearly(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "ocr_enabled", False)
    doc = fitz.open()
    page = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 40, 40), 0)
    pix.clear_with(200)
    page.insert_image(page.rect, pixmap=pix)
    path = tmp_path / "scan.pdf"
    doc.save(path)
    with pytest.raises(ExtractionError, match="scanned"):
        text_extractor.extract_document(path)


# ── Word, PowerPoint ─────────────────────────────────────────────────────────

def test_docx_keeps_reading_order_lists_and_merged_cells(tmp_path):
    from docx import Document

    doc = Document()
    doc.add_heading("Loan policy", level=1)
    doc.add_paragraph("Eligibility is assessed per household.")
    tbl = doc.add_table(rows=3, cols=3)
    for r, row in enumerate([["Tier", "Limit", "Tenure"], ["A", "50000", ""], ["B", "30000", ""]]):
        for c, value in enumerate(row):
            tbl.cell(r, c).text = value
    tbl.cell(1, 2).merge(tbl.cell(2, 2)).text = "12"  # vertically merged
    tbl.cell(0, 0).merge(tbl.cell(0, 0))
    doc.add_paragraph("Documents required:")
    doc.add_paragraph("Aadhaar card", style="List Bullet")
    doc.add_paragraph("Bank passbook", style="List Bullet")
    doc.add_heading("Repayment", level=2)
    doc.add_paragraph("Weekly instalments.")
    path = tmp_path / "policy.docx"
    doc.save(path)

    structure = text_extractor.extract_document(path)
    assert _types(structure) == ["heading", "text", "table", "text", "list", "heading", "text"]
    table = structure.elements[2]
    assert table.metadata["header"] == ["Tier", "Limit", "Tenure"]
    # A vertically merged value belongs to every row it spans.
    assert table.metadata["rows"] == [["A", "50000", "12"], ["B", "30000", "12"]]
    assert structure.elements[4].content == "- Aadhaar card\n- Bank passbook"
    assert all(e.page_number is None for e in structure.elements)  # no invented "page 1"


def test_pptx_slides_titles_bullets_tables_and_notes(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches

    deck = Presentation()
    slide = deck.slides.add_slide(deck.slide_layouts[1])
    slide.shapes.title.text = "Collection targets"
    body = slide.placeholders[1].text_frame
    body.text = "Weekly target 98%"
    sub = body.add_paragraph()
    sub.text = "Follow up within 24 hours"
    sub.level = 1
    rows = slide.shapes.add_table(2, 2, Inches(1), Inches(4), Inches(4), Inches(1)).table
    for (r, c), value in {(0, 0): "Bucket", (0, 1): "Action", (1, 0): "1-30 DPD", (1, 1): "Visit"}.items():
        rows.cell(r, c).text = value
    slide.notes_slide.notes_text_frame.text = "Stress empathy."
    path = tmp_path / "deck.pptx"
    deck.save(path)

    structure = text_extractor.extract_document(path)
    assert structure.elements[0].content == "Collection targets" and structure.elements[0].page_number == 1
    contents = [e.content for e in structure.elements]
    assert "- Weekly target 98%\n  - Follow up within 24 hours" in contents
    assert any(e.element_type == "table" and e.metadata["header"] == ["Bucket", "Action"] for e in structure.elements)
    assert "Speaker notes: Stress empathy." in contents


# ── Spreadsheets, CSV ────────────────────────────────────────────────────────

def test_xlsx_visible_sheets_clean_cells_and_headers(tmp_path):
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Rates"
    sheet.append(["Product", None, "Rate", "Effective"])
    sheet.append(["Group loan", None, 24.0, date(2026, 4, 1)])
    sheet.append([None, None, None, None])
    sheet.append(["Gold loan", None, 18.5, date(2026, 4, 1)])
    hidden = book.create_sheet("Lookup")
    hidden.append(["internal", "codes"])
    hidden.sheet_state = "hidden"
    path = tmp_path / "rates.xlsx"
    book.save(path)

    structure = text_extractor.extract_document(path)
    assert [e.content for e in structure.elements if e.element_type == "heading"] == ["Rates"]
    table = next(e for e in structure.elements if e.element_type == "table")
    assert table.metadata["header"] == ["Product", "Rate", "Effective"]   # empty column dropped
    assert table.metadata["rows"] == [["Group loan", "24", "2026-04-01"], ["Gold loan", "18.5", "2026-04-01"]]


def test_csv_detects_delimiter_and_legacy_encoding(tmp_path):
    path = tmp_path / "branches.csv"
    path.write_bytes("Branch;Manager;Région\nPune;Anil;Ouest\nNagpur;Rekha;Centre\n".encode("cp1252"))
    structure = text_extractor.extract_document(path)
    table = structure.elements[0]
    assert table.metadata["header"] == ["Branch", "Manager", "Région"]
    assert table.metadata["rows"][1] == ["Nagpur", "Rekha", "Centre"]


def test_fake_legacy_office_file_is_refused(tmp_path):
    path = tmp_path / "export.xls"
    path.write_text("<html><table><tr><td>1</td></tr></table></html>")
    with pytest.raises(ExtractionError, match="not a legacy Office"):
        text_extractor.extract_document(path)


# ── Markdown, HTML, text ─────────────────────────────────────────────────────

def test_markdown_structure_and_inline_noise(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text(
        "---\ntitle: Guide\n---\n# Field guide\n\nVisit the [centre](http://x) **every** week.\n"
        "<!-- internal note -->\n\n## Checklist\n- Attendance\n  - Signatures\n- Cash\n\n"
        "```\nrun report\n```\n\n| Day | Task |\n|---|---|\n| Mon | Visits |\n",
        encoding="utf-8",
    )
    structure = text_extractor.extract_document(path)
    assert _types(structure) == ["heading", "text", "heading", "list", "code", "table"]
    assert structure.elements[1].content == "Visit the centre every week."
    assert structure.elements[3].content == "- Attendance\n  - Signatures\n- Cash"
    assert "title: Guide" not in " ".join(e.content for e in structure.elements)


def test_html_reads_main_content_only(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(
        "<html><head><title>Policy</title><style>p{}</style></head><body>"
        "<nav><a>Home</a><a>About</a></nav><header>Site banner</header>"
        "<main><h1>Leave policy</h1><p>Employees get <b>24</b> days.</p>"
        "<div hidden>secret draft</div><ul><li>Casual</li><li>Sick<ul><li>Certified</li></ul></li></ul>"
        "<table><tr><th>Type</th><th>Days</th></tr><tr><td>Casual</td><td>12</td></tr></table></main>"
        "<footer>Copyright</footer><script>track()</script></body></html>",
        encoding="utf-8",
    )
    structure = text_extractor.extract_document(path)
    text = " ".join(e.content for e in structure.elements)
    for noise in ("Home", "Site banner", "secret draft", "Copyright", "track"):
        assert noise not in text
    assert structure.elements[0].content == "Leave policy"
    assert "Employees get 24 days." in text
    assert "- Casual\n- Sick\n  - Certified" in text
    assert structure.metadata["title"] == "Policy"


def test_text_encoding_and_wrapped_lines(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_bytes("The café opens at nine for staff manage-\nment meetings.\n\nPage 2\n".encode("cp1252"))
    structure = text_extractor.extract_document(path)
    assert [e.content for e in structure.elements] == ["The café opens at nine for staff management meetings."]


# ── Safety ───────────────────────────────────────────────────────────────────

def test_renamed_binary_is_not_parsed(tmp_path):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"MZ\x90\x00 not a pdf")
    with pytest.raises(ExtractionError, match="not a valid PDF"):
        text_extractor.extract_document(path)


def test_zip_bomb_office_file_is_refused(tmp_path):
    path = tmp_path / "bomb.docx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", b"0" * 30_000_000)
    with pytest.raises(ExtractionError, match="unsafe size"):
        text_extractor.extract_document(path)


# ── Cleaning ─────────────────────────────────────────────────────────────────

def test_noise_lines_and_repeating_headers():
    assert cleaning.is_noise_line("Page 3 of 12") and cleaning.is_noise_line("- 7 -")
    assert cleaning.is_noise_line("Introduction ............ 4")
    assert cleaning.is_noise_line("")
    assert not cleaning.is_noise_line("Section 3 covers 12 products.")
    bodies = ["Loans are reviewed", "Groups meet weekly", "Cash is counted", "Visits are logged", "Audits run"]
    pages = [["ACME CONFIDENTIAL", bodies[i - 1], f"{i}"] for i in range(1, 6)]
    repeating = cleaning.repeating_lines(pages)
    assert cleaning.is_repeating("ACME CONFIDENTIAL", repeating)
    assert cleaning.is_repeating("9", repeating)  # bare page number at the page edge
    assert not cleaning.is_repeating("Cash is counted", repeating)
    assert not cleaning.is_noise_line("24")  # a bare number can be data


def test_dehyphenation_keeps_real_hyphens():
    joined = cleaning.join_wrapped_lines(["Risk manage-", "ment for e-", "KYC and COVID-", "19 cases"])
    assert joined == "Risk management for e-KYC and COVID-19 cases"
    assert cleaning.clean_block("e-\nKYC") == "e-KYC"
    assert cleaning.clean_block("manage-\nment") == "management"


# ── Chunking ─────────────────────────────────────────────────────────────────

def _structure(elements):
    return DocumentStructure(elements=elements, total_pages=1, has_tables=False, has_images=False)


def test_chunking_never_drops_text_and_keeps_sections(monkeypatch):
    chunker = SemanticChunker()
    chunker.chunk_size, chunker.chunk_overlap, chunker.min_chunk_size = 60, 10, 20
    paragraph = "Joint liability groups meet weekly to repay loans and discuss savings plans together. " * 3
    elements = [
        heading("Operations", 1), ExtractedElement(paragraph, "text", 1),
        heading("Step 1", 2), ExtractedElement("Verify identity.", "text", 2),
        heading("Step 2", 2), ExtractedElement("Record attendance.", "text", 2),
        heading("Closing", 1), ExtractedElement("Tail.", "text", 3),
    ]
    chunks = chunker.chunk_document(_structure(elements))
    joined = _norm(" ".join(c.content for c in chunks))
    for text in ("verify identity", "record attendance", "tail", "step 2", "closing"):
        assert text in joined
    steps = next(c for c in chunks if "Verify identity" in c.content)
    assert "Record attendance" in steps.content  # small sibling steps packed together
    assert all(c.section_title for c in chunks)
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    # Overlap never carries text across a section boundary.
    closing = next(c for c in chunks if c.section_title == "Closing")
    assert "Joint liability" not in closing.content


def test_heading_only_sections_are_not_lost():
    chunks = SemanticChunker().chunk_document(_structure([
        heading("Annexure", 1), heading("Forms", 2), ExtractedElement("Form A is used for KYC.", "text"),
        heading("Glossary", 1),
    ]))
    joined = " ".join(c.content for c in chunks)
    assert "Annexure" in joined and "Forms" in joined and "Glossary" in joined


def test_long_tables_repeat_the_header_in_every_part():
    header = ["Branch", "Officer", "Portfolio"]
    rows = [[f"Branch {i}", f"Officer {i}", str(i * 1000)] for i in range(200)]
    parts = split_markdown(header, rows, max_tokens=300, count_tokens=SemanticChunker().count_tokens)
    assert len(parts) > 2
    assert all(part.startswith("| Branch | Officer | Portfolio |\n| --- |") for part in parts)
    assert sum(part.count("| Branch ") - 1 for part in parts) == 200  # every row exactly once
