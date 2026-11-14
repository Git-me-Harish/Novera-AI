"""Word (.docx, legacy .doc) and PowerPoint (.pptx).

Word keeps the body in reading order: paragraphs and tables interleaved as
the author wrote them (tables used to be appended after all text, detached
from their section). Heading styles become section headings, list styles
become list items, and horizontally merged cells are read once.

Legacy .doc is converted to .docx with LibreOffice (headless) and then read
by the same code, so both formats keep headings and tables.

PowerPoint is read slide by slide: the slide title is a heading, shapes are
read top-to-bottom then left-to-right, bullets keep their indent level, and
tables and speaker notes are included.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator, Optional

from loguru import logger

from app.services.document_processing.cleaning import clean_block, normalize
from app.services.document_processing.elements import (
    DocumentStructure,
    ExtractedElement,
    ExtractionError,
    heading,
    table,
)
from app.services.document_processing.tables import clean_rows, split_header

LIBREOFFICE_TIMEOUT_SECONDS = 180


# ── Word ─────────────────────────────────────────────────────────────────────

def _heading_level(style_name: str) -> Optional[int]:
    name = (style_name or "").lower()
    if name == "title":
        return 1
    if name.startswith("heading"):
        digits = "".join(ch for ch in name if ch.isdigit())
        return int(digits) if digits else 1
    return None


def _is_list(paragraph) -> bool:
    style = (paragraph.style.name if paragraph.style is not None else "").lower()
    if "list" in style:
        return True
    p_pr = paragraph._p.pPr
    return p_pr is not None and p_pr.numPr is not None


def _docx_table_rows(tbl) -> list[list[str]]:
    rows = []
    for row in tbl.rows:
        cells, seen = [], set()
        for cell in row.cells:
            # Merged cells come back as the same underlying element.
            key = id(cell._tc)
            cells.append("" if key in seen else cell.text)
            seen.add(key)
        rows.append(cells)
    return rows


def extract_docx(path: Path) -> DocumentStructure:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = Document(path)
    except Exception as exc:
        raise ExtractionError("This Word document could not be opened; it may be damaged.") from exc

    elements: list[ExtractedElement] = []
    list_buffer: list[str] = []

    def flush_list() -> None:
        if list_buffer:
            elements.append(ExtractedElement("\n".join(list_buffer), "list"))
            list_buffer.clear()

    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = Paragraph(child, doc)
            text = clean_block(paragraph.text)
            if not text:
                continue
            level = _heading_level(paragraph.style.name if paragraph.style is not None else "")
            if level:
                flush_list()
                elements.append(heading(" ".join(text.split()), level))
            elif _is_list(paragraph):
                list_buffer.append(f"- {' '.join(text.split())}")
            else:
                flush_list()
                elements.append(ExtractedElement(text, "text"))
        elif tag == "tbl":
            flush_list()
            rows = clean_rows(_docx_table_rows(Table(child, doc)))
            if rows:
                header, data = split_header(rows)
                elements.append(table(header, data))
    flush_list()

    return DocumentStructure(
        elements=elements,
        total_pages=0,
        has_tables=any(e.element_type == "table" for e in elements),
        has_images=bool(doc.inline_shapes),
        metadata={"extraction_method": "docx"},
    )


def _libreoffice() -> Optional[str]:
    return shutil.which("soffice") or shutil.which("libreoffice")


def extract_doc(path: Path) -> DocumentStructure:
    binary = _libreoffice()
    if not binary:
        raise ExtractionError(
            "Legacy .doc files need LibreOffice on the server. Save the file as .docx and upload again."
        )
    with tempfile.TemporaryDirectory(prefix="novera-doc-") as workdir:
        try:
            subprocess.run(
                # A private profile: concurrent conversions otherwise fight
                # over the default one and fail intermittently.
                [binary, f"-env:UserInstallation=file:///{Path(workdir).as_posix()}/profile",
                 "--headless", "--norestore", "--convert-to", "docx", "--outdir", workdir, str(path)],
                check=True, capture_output=True, timeout=LIBREOFFICE_TIMEOUT_SECONDS,
                # The service user has no home directory; LibreOffice needs a
                # writable one for its caches.
                env={**os.environ, "HOME": workdir},
            )
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError("Converting this .doc file took too long.") from exc
        except subprocess.CalledProcessError as exc:
            logger.warning(f"LibreOffice conversion failed: exit {exc.returncode}")
            raise ExtractionError("This .doc file could not be converted; it may be damaged.") from exc
        converted = Path(workdir) / f"{path.stem}.docx"
        if not converted.exists():
            raise ExtractionError("This .doc file could not be converted; it may be damaged.")
        structure = extract_docx(converted)
    structure.metadata["extraction_method"] = "doc_via_libreoffice"
    return structure


# ── PowerPoint ───────────────────────────────────────────────────────────────

def _shapes_in_reading_order(shapes) -> Iterator:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    ordered = sorted(shapes, key=lambda s: ((s.top or 0) // 50_000, s.left or 0))
    for shape in ordered:
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _shapes_in_reading_order(shape.shapes)
        else:
            yield shape


def extract_pptx(path: Path) -> DocumentStructure:
    from pptx import Presentation

    try:
        deck = Presentation(path)
    except Exception as exc:
        raise ExtractionError("This PowerPoint file could not be opened; it may be damaged.") from exc

    elements: list[ExtractedElement] = []
    for number, slide in enumerate(deck.slides, start=1):
        title_shape = slide.shapes.title
        title = " ".join(normalize(title_shape.text).split()) if title_shape is not None and title_shape.has_text_frame else ""
        elements.append(heading(title or f"Slide {number}", 1, number))
        for shape in _shapes_in_reading_order(slide.shapes):
            if title_shape is not None and shape.shape_id == title_shape.shape_id:
                continue
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = clean_rows([[cell.text for cell in row.cells] for row in shape.table.rows])
                if rows:
                    header, data = split_header(rows)
                    elements.append(table(header, data, number))
            elif getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                paragraphs = [
                    (p.level, " ".join(normalize("".join(run.text for run in p.runs)).split()))
                    for p in shape.text_frame.paragraphs
                ]
                paragraphs = [(level, text) for level, text in paragraphs if text]
                if not paragraphs:
                    continue
                if len(paragraphs) == 1:
                    elements.append(ExtractedElement(paragraphs[0][1], "text", number))
                else:
                    lines = [f"{'  ' * level}- {text}" for level, text in paragraphs]
                    elements.append(ExtractedElement("\n".join(lines), "list", number))
        if slide.has_notes_slide:
            notes = clean_block(slide.notes_slide.notes_text_frame.text or "")
            if notes:
                elements.append(ExtractedElement(f"Speaker notes: {notes}", "text", number))

    return DocumentStructure(
        elements=elements,
        total_pages=len(deck.slides),
        has_tables=any(e.element_type == "table" for e in elements),
        has_images=False,
        metadata={"extraction_method": "pptx"},
    )
