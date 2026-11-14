"""Document text extraction: one entry point over the per-format parsers.

Supported: PDF (with OCR for scanned pages), Word (.docx, legacy .doc),
PowerPoint (.pptx), Excel (.xlsx, .xls), CSV, Markdown, HTML and text.
Each parser lives in ``formats/`` and returns ordered, typed elements (see
``elements.py``); this module checks the file is what its extension says,
dispatches, and refuses files that yield no text instead of indexing an
empty document as "completed".
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from app.services.document_processing.elements import (
    DocumentStructure,
    ExtractedElement,
    ExtractionError,
)
from app.services.document_processing.formats import PARSERS
from app.services.document_processing.formats.common import check_signature

SUPPORTED_EXTENSIONS = frozenset(PARSERS)


class TextExtractor:
    supported_formats = set(SUPPORTED_EXTENSIONS)

    def extract_document(self, file_path: Path) -> DocumentStructure:
        file_path = Path(file_path)
        ext = file_path.suffix.lower()
        parser = PARSERS.get(ext)
        if parser is None:
            raise ExtractionError(f"{ext or 'This file type'} files are not supported.")
        check_signature(file_path, ext)
        logger.info(f"Extracting {ext} document")
        structure = parser(file_path)
        if structure.text_length == 0:
            raise ExtractionError("No readable text was found in this file.")
        structure.metadata.setdefault("element_counts", {})
        for element in structure.elements:
            counts = structure.metadata["element_counts"]
            counts[element.element_type] = counts.get(element.element_type, 0) + 1
        logger.info(
            f"Extracted {len(structure.elements)} elements "
            f"({structure.metadata['element_counts']}) via {structure.metadata.get('extraction_method')}"
        )
        return structure

    def extract_text_only(self, file_path: Path) -> str:
        return "\n\n".join(e.content for e in self.extract_document(file_path).elements)


text_extractor = TextExtractor()

__all__ = [
    "TextExtractor", "text_extractor", "ExtractedElement", "DocumentStructure",
    "ExtractionError", "SUPPORTED_EXTENSIONS",
]
