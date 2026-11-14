"""The contract between format parsers and the chunker.

Every parser turns a file into an ordered list of elements:

  heading  a section title; ``metadata["level"]`` 1 (top) .. 6
  text     a paragraph
  list     one or more list items, one per line, each starting with "- "
  code     preformatted text, kept verbatim
  table    Markdown; ``metadata["header"]`` and ``metadata["rows"]`` hold
           the cells so the chunker can split it and repeat the header

``page_number`` is the 1-based page or slide, or None for formats without
pages (Word, spreadsheets, Markdown, HTML) — a guessed "page 1" made
citations point to the wrong place.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ELEMENT_TYPES = {"heading", "text", "list", "code", "table"}


class ExtractionError(Exception):
    """A file cannot be read. The message is safe to show to the uploader."""


@dataclass
class ExtractedElement:
    content: str
    element_type: str
    page_number: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "element_type": self.element_type,
            "page_number": self.page_number,
            "metadata": self.metadata,
        }


@dataclass
class DocumentStructure:
    elements: List[ExtractedElement]
    total_pages: int
    has_tables: bool
    has_images: bool
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_elements_by_type(self, element_type: str) -> List[ExtractedElement]:
        return [e for e in self.elements if e.element_type == element_type]

    def get_elements_by_page(self, page_num: int) -> List[ExtractedElement]:
        return [e for e in self.elements if e.page_number == page_num]

    @property
    def text_length(self) -> int:
        return sum(len(e.content) for e in self.elements)


def heading(text: str, level: int, page: Optional[int] = None) -> ExtractedElement:
    return ExtractedElement(text, "heading", page, {"level": max(1, min(6, level))})


def table(header: list[str], rows: list[list[str]], page: Optional[int] = None, **meta: Any) -> ExtractedElement:
    from app.services.document_processing.tables import to_markdown

    return ExtractedElement(to_markdown(header, rows), "table", page, {"header": header, "rows": rows, **meta})
