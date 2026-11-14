"""One parser per file family; ``PARSERS`` maps an extension to it."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from app.services.document_processing.elements import DocumentStructure
from app.services.document_processing.formats.markup import extract_html, extract_markdown
from app.services.document_processing.formats.office import extract_doc, extract_docx, extract_pptx
from app.services.document_processing.formats.pdf import extract_pdf
from app.services.document_processing.formats.plain import extract_txt
from app.services.document_processing.formats.sheets import extract_csv, extract_xls, extract_xlsx

PARSERS: dict[str, Callable[[Path], DocumentStructure]] = {
    ".pdf": extract_pdf,
    ".docx": extract_docx,
    ".doc": extract_doc,
    ".pptx": extract_pptx,
    ".xlsx": extract_xlsx,
    ".xls": extract_xls,
    ".csv": extract_csv,
    ".md": extract_markdown,
    ".markdown": extract_markdown,
    ".html": extract_html,
    ".htm": extract_html,
    ".txt": extract_txt,
}

__all__ = ["PARSERS"]
