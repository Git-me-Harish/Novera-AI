"""Structure-aware chunking.

Chunks follow the document's own structure, because a chunk is the unit of
retrieval, citation and evidence:

* A heading starts a new section; the section path ("Pricing › Fees") is
  stored with every chunk and is part of its embedding text.
* Within a section, paragraphs and list items are packed up to
  CHUNK_SIZE tokens without breaking them; only an over-long paragraph is
  split, at sentence boundaries. Overlap repeats the last sentences of the
  previous chunk, never across sections.
* Nothing is dropped. A short section stays its own (precise) chunk; a short
  tail of a long section joins the previous chunk of that section.
* Tables are chunked on their own; a split table repeats its header row.

Previously a document's text was one stream: 0 of 210 stored chunks had a
section, chunks averaged ~770 tokens across 3.4 pages, short trailing text
under MIN_CHUNK_SIZE was discarded, and a metadata-only "summary" chunk per
document competed with real evidence in search.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import tiktoken
from loguru import logger

from app.core.config import settings
from app.services.document_processing.elements import DocumentStructure, ExtractedElement
from app.services.document_processing.tables import split_markdown

SECTION_SEPARATOR = " › "
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


@dataclass
class Chunk:
    content: str
    chunk_type: str
    chunk_index: int
    page_numbers: List[int]
    section_title: Optional[str]
    token_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "chunk_type": self.chunk_type,
            "chunk_index": self.chunk_index,
            "page_numbers": self.page_numbers,
            "section_title": self.section_title,
            "token_count": self.token_count,
            "metadata": self.metadata,
        }


MAX_PATH_DEPTH = 3


@dataclass
class _Unit:
    """A section (heading + body) or a table, before it is cut into chunks."""
    path: List[str]
    heading: Optional[str]
    elements: List[ExtractedElement] = field(default_factory=list)
    table: Optional[ExtractedElement] = None
    caption: Optional[str] = None
    tokens: int = 0


def _common_prefix(a: List[str], b: List[str]) -> List[str]:
    prefix = []
    for x, y in zip(a, b):
        if x != y:
            break
        prefix.append(x)
    return prefix


def _related(a: List[str], b: List[str]) -> bool:
    """Siblings, or b nested under a."""
    if not a or not b:
        return a == b
    nested = b[: len(a)] == a
    # Siblings must share a real parent; top-level chapters stay apart.
    siblings = len(a) == len(b) >= 2 and a[:-1] == b[:-1]
    return nested or siblings


def _display_path(path: List[str]) -> Optional[str]:
    # The most specific levels identify a section; deeper ancestry is noise.
    return SECTION_SEPARATOR.join(path[-MAX_PATH_DEPTH:]) or None


def _first_page(unit: "_Unit") -> Optional[int]:
    return next((e.page_number for e in unit.elements if e.page_number is not None), None)


@dataclass
class _Piece:
    text: str
    page: Optional[int]
    tokens: int
    joiner: str  # how this piece attaches to the one before it


class SemanticChunker:
    def __init__(self) -> None:
        self.chunk_size = settings.chunk_size
        self.chunk_overlap = settings.chunk_overlap
        self.max_table_tokens = settings.max_table_tokens
        self.min_chunk_size = settings.min_chunk_size
        try:
            self.encoding = tiktoken.encoding_for_model("gpt-4")
        except Exception:
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    # ── public ────────────────────────────────────────────────────────────

    def chunk_document(
        self, doc_structure: DocumentStructure, document_title: Optional[str] = None
    ) -> List[Chunk]:
        units = self._section_units(doc_structure.elements)
        units = self._pack_small_sections(units)
        units = self._caption_tables(units)

        chunks: List[Chunk] = []
        for unit in units:
            path = _display_path(unit.path)
            if unit.table is not None:
                chunks.extend(self._chunk_table(unit.table, path, unit.caption))
            else:
                chunks.extend(self._chunk_section(unit.elements, path, unit.heading))
        for index, chunk in enumerate(chunks):
            chunk.chunk_index = index
        logger.info(
            f"Created {len(chunks)} chunks "
            f"({sum(1 for c in chunks if c.section_title)} with a section)"
        )
        return chunks

    # ── structure ─────────────────────────────────────────────────────────

    def _section_units(self, elements: List[ExtractedElement]) -> List["_Unit"]:
        """Split the element stream at headings and tables."""
        units: List[_Unit] = []
        stack: list[tuple[int, str]] = []
        current = _Unit(path=[], heading=None)
        for element in elements:
            kind = element.element_type
            if kind == "heading":
                if current.elements or current.heading:
                    units.append(current)
                level = int(element.metadata.get("level", 1))
                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, element.content.strip()))
                current = _Unit(path=[text for _, text in stack], heading=element.content.strip())
            elif kind == "table":
                if current.elements or current.heading:
                    units.append(current)
                units.append(_Unit(path=list(current.path), heading=None, table=element))
                current = _Unit(path=list(current.path), heading=None)
            else:
                current.elements.append(element)
        if current.elements or current.heading:
            units.append(current)
        for unit in units:
            unit.tokens = self._unit_tokens(unit)
        return units

    def _unit_tokens(self, unit: "_Unit") -> int:
        if unit.table is not None:
            return self.count_tokens(unit.table.content)
        body = sum(self.count_tokens(e.content) for e in unit.elements)
        return body + (self.count_tokens(unit.heading) if unit.heading else 0)

    def _pack_small_sections(self, units: List["_Unit"]) -> List["_Unit"]:
        """Join small sibling sections (and a heading with its sub-sections).

        "Step 1 … Step 4" under one procedure, or a heading immediately
        followed by sub-headings, belong in one chunk: retrieved apart, each
        piece answers only part of the question.
        """
        packed: List[_Unit] = []
        for unit in units:
            previous = packed[-1] if packed else None
            if previous is not None and previous.table is None and unit.table is None and not previous.elements:
                # A heading with no body of its own introduces what follows.
                if unit.heading:
                    unit.elements.insert(0, ExtractedElement(unit.heading, "text", _first_page(unit)))
                unit.heading = previous.heading
                unit.path = previous.path if _related(previous.path, unit.path) else unit.path
                unit.tokens += previous.tokens
                packed[-1] = unit
                continue
            if (
                previous is not None
                and previous.table is None and unit.table is None
                and previous.tokens < self.min_chunk_size
                and previous.tokens + unit.tokens <= self.chunk_size
                and _related(previous.path, unit.path)
            ):
                if unit.heading:
                    previous.elements.append(ExtractedElement(unit.heading, "text", _first_page(unit)))
                previous.elements.extend(unit.elements)
                previous.path = _common_prefix(previous.path, unit.path) or previous.path
                previous.tokens += unit.tokens
                continue
            packed.append(unit)
        return packed

    def _caption_tables(self, units: List["_Unit"]) -> List["_Unit"]:
        """A short lead-in ("The grid below defines…") captions its table."""
        out: List[_Unit] = []
        for unit in units:
            previous = out[-1] if out else None
            if (
                unit.table is not None
                and previous is not None
                and previous.table is None
                and previous.path == unit.path
                and previous.tokens <= self.min_chunk_size
            ):
                lines = ([previous.heading] if previous.heading else []) + [e.content for e in previous.elements]
                unit.caption = "\n".join(lines)
                out.pop()
            elif unit.table is not None and unit.caption is None and unit.path:
                unit.caption = unit.path[-1]
            out.append(unit)
        return out

    # ── sections ──────────────────────────────────────────────────────────

    def _pieces(self, elements: List[ExtractedElement]) -> List[_Piece]:
        """Paragraphs and list items, split further only when over-long."""
        pieces: List[_Piece] = []
        for element in elements:
            units = element.content.split("\n") if element.element_type == "list" else [element.content]
            for position, unit in enumerate(units):
                unit = unit.strip("\n") if element.element_type == "code" else unit.strip()
                if not unit:
                    continue
                joiner = "\n" if element.element_type == "list" and position else "\n\n"
                tokens = self.count_tokens(unit)
                if tokens <= self.chunk_size or element.element_type == "code":
                    pieces.append(_Piece(unit, element.page_number, tokens, joiner))
                    continue
                for i, sentence in enumerate(self._split_long(unit)):
                    pieces.append(_Piece(sentence, element.page_number,
                                         self.count_tokens(sentence), joiner if i == 0 else " "))
        return pieces

    def _chunk_section(
        self, elements: List[ExtractedElement], section_path: Optional[str], heading: Optional[str]
    ) -> List[Chunk]:
        pieces = self._pieces(elements)
        if not pieces:
            if not heading:
                return []
            # A trailing heading with nothing under it is still content.
            pieces, heading = [_Piece(heading, None, self.count_tokens(heading), "\n\n")], None
        # The heading opens the section's first chunk, so the words a user
        # would search for are in the text itself, not only in metadata.
        if heading:
            pieces[0] = _Piece(f"{heading}\n{pieces[0].text}", pieces[0].page,
                               pieces[0].tokens + self.count_tokens(heading) + 1, pieces[0].joiner)

        groups: List[List[_Piece]] = []
        current: List[_Piece] = []
        tokens = 0
        for piece in pieces:
            if current and tokens + piece.tokens > self.chunk_size:
                groups.append(current)
                overlap = self._overlap(current)
                current = overlap + [piece]
                tokens = sum(p.tokens for p in current)
            else:
                current.append(piece)
                tokens += piece.tokens
        if current:
            previous = groups[-1] if groups else []
            fresh = [p for p in current if not any(p is q for q in previous)]  # minus the overlap
            fresh_tokens = sum(p.tokens for p in fresh)
            if groups and fresh_tokens < self.min_chunk_size:
                # Never drop a short tail; attach it to its predecessor.
                groups[-1].extend(fresh)
            else:
                groups.append(current)

        return [self._make_chunk(group, "text", section_path) for group in groups]

    def _overlap(self, pieces: List[_Piece]) -> List[_Piece]:
        if self.chunk_overlap <= 0:
            return []
        kept: List[_Piece] = []
        total = 0
        for piece in reversed(pieces):
            if total + piece.tokens > self.chunk_overlap:
                break
            kept.insert(0, piece)
            total += piece.tokens
        # Overlap must not be the whole previous chunk.
        return kept if len(kept) < len(pieces) else kept[1:]

    def _make_chunk(self, pieces: List[_Piece], chunk_type: str, section_path: Optional[str]) -> Chunk:
        text = pieces[0].text
        for piece in pieces[1:]:
            text += piece.joiner + piece.text
        pages = sorted({p.page for p in pieces if p.page is not None})
        return Chunk(
            content=text.strip(),
            chunk_type=chunk_type,
            chunk_index=0,
            page_numbers=pages,
            section_title=section_path,
            token_count=self.count_tokens(text),
            metadata={"char_count": len(text), "has_numbers": any(ch.isdigit() for ch in text)},
        )

    # ── tables ────────────────────────────────────────────────────────────

    def _chunk_table(
        self, element: ExtractedElement, section_path: Optional[str], caption_text: Optional[str]
    ) -> List[Chunk]:
        header = element.metadata.get("header")
        rows = element.metadata.get("rows")
        caption = f"{caption_text}\n" if caption_text else ""
        if header is None or rows is None:
            parts = [element.content]
        else:
            parts = split_markdown(
                header, rows,
                max_tokens=max(200, self.max_table_tokens - self.count_tokens(caption)),
                count_tokens=self.count_tokens,
            )
        pages = [element.page_number] if element.page_number is not None else []
        chunks = []
        for index, part in enumerate(parts, start=1):
            content = f"{caption}{part}"
            meta = {"char_count": len(content), "has_numbers": True}
            if len(parts) > 1:
                meta["table_part"] = f"{index}/{len(parts)}"
            for key in ("sheet",):
                if key in element.metadata:
                    meta[key] = element.metadata[key]
            chunks.append(Chunk(content, "table", 0, pages, section_path, self.count_tokens(content), meta))
        return chunks

    # ── splitting ─────────────────────────────────────────────────────────

    def _split_long(self, text: str) -> List[str]:
        """Sentences, and word windows for sentences longer than a chunk."""
        out: List[str] = []
        for sentence in _SENTENCE_END.split(text):
            if self.count_tokens(sentence) <= self.chunk_size:
                out.append(sentence)
                continue
            words, window = sentence.split(), []
            for word in words:
                window.append(word)
                if self.count_tokens(" ".join(window)) >= self.chunk_size:
                    out.append(" ".join(window))
                    window = []
            if window:
                out.append(" ".join(window))
        return out

    # Kept for callers that split arbitrary text.
    def _split_sentences(self, text: str) -> List[str]:
        return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


semantic_chunker = SemanticChunker()

__all__ = ["Chunk", "SemanticChunker", "semantic_chunker", "SECTION_SEPARATOR"]
