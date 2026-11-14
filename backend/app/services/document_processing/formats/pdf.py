"""PDF: layout-aware text, real tables, headings from typography, and OCR.

* Headings come from font size and weight relative to the body text, so a
  document's own structure becomes the chunk's section path.
* Ruled tables are read cell by cell (PyMuPDF ``find_tables``) and their
  text is not repeated as loose lines.
* Running headers/footers, page numbers and table-of-contents leaders are
  dropped before chunking.
* Pages without a text layer are OCR'd with Tesseract when it is installed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Optional

import fitz  # PyMuPDF
from loguru import logger

from app.core.config import settings
from app.services.document_processing.cleaning import (
    is_noise_line,
    is_repeating,
    join_wrapped_lines,
    normalize,
    repeating_lines,
)
from app.services.document_processing.elements import (
    DocumentStructure,
    ExtractedElement,
    ExtractionError,
    heading,
    table,
)
from app.services.document_processing.tables import clean_rows, split_header

MIN_TEXT_CHARS_PER_PAGE = 25  # below this a page is treated as scanned
HEADING_SIZE_RATIO = 1.12
MAX_HEADING_WORDS = 18


def _is_bold(span: dict) -> bool:
    return bool(span.get("flags", 0) & 16) or "bold" in span.get("font", "").lower()


def _ocr_textpage(page: "fitz.Page") -> Optional["fitz.TextPage"]:
    if not settings.ocr_enabled:
        return None
    try:
        return page.get_textpage_ocr(language=settings.ocr_languages, dpi=settings.ocr_dpi, full=True)
    except Exception as exc:  # Tesseract missing or failing: report, never crash
        logger.warning(f"OCR unavailable on page {page.number + 1}: {type(exc).__name__}")
        return None


def _lines(block: dict) -> list[dict]:
    lines = []
    for line in block.get("lines", []):
        spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
        if not spans:
            continue
        text = "".join(s["text"] for s in line["spans"])
        lines.append({
            "text": normalize(text).strip(),
            "size": round(max(s["size"] for s in spans) * 2) / 2,
            "bold": all(_is_bold(s) for s in spans),
            "y": line["bbox"][1],
        })
    return lines


def _inside(bbox, boxes) -> bool:
    x0, y0, x1, y1 = bbox
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)


def extract_pdf(path: Path) -> DocumentStructure:
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ExtractionError("This PDF could not be opened; it may be damaged.") from exc
    if doc.needs_pass:
        raise ExtractionError("This PDF is password-protected. Remove the password and upload again.")

    pages: list[dict[str, Any]] = []
    ocr_pages: list[int] = []
    unreadable_pages: list[int] = []
    has_images = False
    for page in doc:
        number = page.number + 1
        images = page.get_images(full=False)
        has_images = has_images or bool(images)
        textpage = None
        if len(page.get_text("text").strip()) < MIN_TEXT_CHARS_PER_PAGE and images:
            textpage = _ocr_textpage(page)
            (ocr_pages if textpage else unreadable_pages).append(number)

        tables: list[dict] = []
        if textpage is None:  # table detection needs a real text layer
            try:
                for found in page.find_tables().tables:
                    rows = clean_rows(found.extract())
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        tables.append({"bbox": tuple(found.bbox), "rows": rows})
            except Exception as exc:
                logger.debug(f"Table detection skipped on page {number}: {type(exc).__name__}")

        blocks = []
        boxes = [t["bbox"] for t in tables]
        for block in page.get_text("dict", textpage=textpage)["blocks"]:
            if block.get("type") != 0 or _inside(block["bbox"], boxes):
                continue
            lines = _lines(block)
            if lines:
                blocks.append({"y": block["bbox"][1], "x": block["bbox"][0], "lines": lines})
        pages.append({"number": number, "blocks": blocks, "tables": tables})
    total_pages = len(doc)
    doc.close()

    if unreadable_pages and len(unreadable_pages) == total_pages:
        raise ExtractionError(
            "This PDF is scanned and has no text layer, and OCR is not available on this server."
        )

    # Body size = the size most characters are set in; headings are larger,
    # or bold at body size.
    sizes: Counter[float] = Counter()
    pages_with_size: dict[float, set[int]] = {}
    for p in pages:
        for b in p["blocks"]:
            for line in b["lines"]:
                sizes[line["size"]] += len(line["text"])
                pages_with_size.setdefault(line["size"], set()).add(p["number"])
    body = sizes.most_common(1)[0][0] if sizes else 10.0
    # A size used on one page only (a cover title, a banner) is decoration,
    # not a structural level; letting it in nested every later section
    # under cover-page text.
    min_pages = 2 if len(pages) > 1 else 1
    heading_sizes = sorted(
        {s for s in sizes if s >= body * HEADING_SIZE_RATIO and len(pages_with_size[s]) >= min_pages},
        reverse=True,
    )
    level_of = {size: index + 1 for index, size in enumerate(heading_sizes[:5])}
    bold_level = min(6, len(level_of) + 1)

    repeating = repeating_lines([[l["text"] for b in p["blocks"] for l in b["lines"]] for p in pages])

    elements: list[ExtractedElement] = []
    for p in pages:
        items = [("block", b["y"], b) for b in p["blocks"]] + [("table", t["bbox"][1], t) for t in p["tables"]]
        for kind, _, item in sorted(items, key=lambda entry: entry[1]):
            if kind == "table":
                header, rows = split_header(item["rows"])
                elements.append(table(header, rows, p["number"]))
                continue
            buffer: list[str] = []

            def flush() -> None:
                if buffer:
                    text = join_wrapped_lines(buffer)
                    if text:
                        is_list = all(line.startswith("- ") for line in text.split("\n"))
                        elements.append(ExtractedElement(text, "list" if is_list else "text", p["number"]))
                    buffer.clear()

            for line in item["lines"]:
                text = line["text"]
                if is_noise_line(text) or is_repeating(text, repeating):
                    continue
                level = _heading_level(line, body, level_of, bold_level)
                if level:
                    flush()
                    elements.append(heading(text, level, p["number"]))
                else:
                    buffer.append(text)
            flush()

    return DocumentStructure(
        elements=_merge_split_headings(elements),
        total_pages=total_pages,
        has_tables=any(e.element_type == "table" for e in elements),
        has_images=has_images,
        metadata={
            "extraction_method": "pymupdf",
            "body_font_size": body,
            "ocr_pages": ocr_pages,
            "unreadable_pages": unreadable_pages,
            "removed_running_lines": len(repeating),
        },
    )


def _heading_level(line: dict, body: float, level_of: dict, bold_level: int) -> Optional[int]:
    text = line["text"]
    words = len(text.split())
    if not text or words > MAX_HEADING_WORDS or text.startswith("- "):
        return None
    # Sentences are not headings; questions are (FAQ entries are sections).
    if text.endswith((".", ",", ";")) and not text.endswith("?"):
        return None
    if line["size"] in level_of:
        return level_of[line["size"]]
    if line["bold"] and line["size"] >= body and words >= 2 and not text.endswith(":"):
        # Bold body-size lines are sub-headings; a lone "Answer:" label is not.
        return bold_level
    return None


def _merge_split_headings(elements: list[ExtractedElement]) -> list[ExtractedElement]:
    """A long title set on two lines arrives as two same-level headings."""
    merged: list[ExtractedElement] = []
    for element in elements:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and element.element_type == "heading" == previous.element_type
            and element.metadata["level"] == previous.metadata["level"]
            and element.page_number == previous.page_number
            and not previous.content.endswith("?")
            and len(previous.content.split()) + len(element.content.split()) <= MAX_HEADING_WORDS
        ):
            previous.content = f"{previous.content} {element.content}"
            continue
        merged.append(element)
    return merged
