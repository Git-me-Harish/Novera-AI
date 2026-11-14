"""Plain text (.txt).

The encoding is detected instead of dropping undecodable bytes. Paragraphs
are separated by blank lines; hard-wrapped lines inside a paragraph are
joined, and list items keep their own lines.
"""
from __future__ import annotations

from pathlib import Path

from app.services.document_processing.cleaning import is_noise_line, join_wrapped_lines, normalize
from app.services.document_processing.elements import DocumentStructure, ExtractedElement, ExtractionError
from app.services.document_processing.formats.common import decode_text


def extract_txt(path: Path) -> DocumentStructure:
    text = normalize(decode_text(path.read_bytes()))
    elements: list[ExtractedElement] = []
    for block in text.split("\n\n"):
        lines = [line for line in block.split("\n") if not is_noise_line(line)]
        paragraph = join_wrapped_lines(lines)
        if not paragraph:
            continue
        is_list = all(line.startswith("- ") for line in paragraph.split("\n"))
        elements.append(ExtractedElement(paragraph, "list" if is_list else "text"))
    if not elements:
        raise ExtractionError("No readable text was found in this file.")
    return DocumentStructure(
        elements=elements, total_pages=0, has_tables=False, has_images=False,
        metadata={"extraction_method": "text"},
    )
