"""Markdown and HTML.

Markdown: headings (ATX and setext), lists, fenced code, pipe tables and
paragraphs. Front matter, HTML comments and raw tags are removed; links and
images keep only their visible text.

HTML: only the main content is read. Scripts, styles, navigation, headers,
footers, sidebars, forms and hidden elements are removed first; <main> or
<article> is preferred over the whole <body>. Headings, paragraphs, lists,
tables and preformatted blocks keep their structure.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from app.services.document_processing.cleaning import clean_block, normalize
from app.services.document_processing.elements import (
    DocumentStructure,
    ExtractedElement,
    ExtractionError,
    heading,
    table,
)
from app.services.document_processing.formats.common import decode_text
from app.services.document_processing.tables import clean_rows, split_header

# ── Markdown ─────────────────────────────────────────────────────────────────

_FRONT_MATTER = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SETEXT = re.compile(r"^(=+|-+)\s*$")
_FENCE = re.compile(r"^(```|~~~)")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_TABLE_SEPARATOR = re.compile(r"^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _inline(text: str) -> str:
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)      # images -> alt text
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)       # links -> text
    text = re.sub(r"<[^>]+>", "", text)                         # inline HTML tags
    text = re.sub(r"(\*\*|__)(.+?)\1", r"\2", text)             # bold
    text = re.sub(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])", r"\2", text)  # italic
    text = re.sub(r"`([^`]+)`", r"\1", text)                    # inline code
    return " ".join(normalize(text).split())


def _split_row(line: str) -> list[str]:
    line = line.strip().strip("|")
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", line)]


def parse_markdown(text: str) -> list[ExtractedElement]:
    text = _COMMENT.sub("", _FRONT_MATTER.sub("", normalize(text)))
    lines = text.split("\n")
    elements: list[ExtractedElement] = []
    paragraph: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if paragraph:
            content = _inline(" ".join(paragraph))
            if content:
                elements.append(ExtractedElement(content, "text"))
            paragraph.clear()
        if items:
            elements.append(ExtractedElement("\n".join(items), "list"))
            items.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if _FENCE.match(stripped):
            flush()
            fence, body = stripped[:3], []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(fence):
                body.append(lines[i])
                i += 1
            if any(b.strip() for b in body):
                elements.append(ExtractedElement("\n".join(body).rstrip(), "code"))
            i += 1
            continue
        match = _ATX.match(stripped)
        if match:
            flush()
            elements.append(heading(_inline(match.group(2)), len(match.group(1))))
            i += 1
            continue
        if (stripped and i + 1 < len(lines) and _SETEXT.match(lines[i + 1].strip())
                and not paragraph and not _LIST.match(line)):
            flush()
            elements.append(heading(_inline(stripped), 1 if lines[i + 1].strip()[0] == "=" else 2))
            i += 2
            continue
        if stripped.startswith("|") and i + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[i + 1].strip()):
            flush()
            rows = [_split_row(stripped)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(_split_row(lines[i]))
                i += 1
            cleaned = clean_rows([[_inline(c) for c in row] for row in rows])
            if cleaned:
                elements.append(table(cleaned[0], cleaned[1:]))
            continue
        match = _LIST.match(line)
        if match:
            if paragraph:
                flush()
            depth = len(match.group(1).expandtabs(4)) // 2
            items.append(f"{'  ' * depth}- {_inline(match.group(3))}")
            i += 1
            continue
        if not stripped:
            flush()
        elif items and line.startswith((" ", "\t")):
            items[-1] += " " + _inline(stripped)  # continuation of a list item
        else:
            if items:
                flush()
            paragraph.append(stripped)
        i += 1
    flush()
    return elements


def extract_markdown(path: Path) -> DocumentStructure:
    elements = parse_markdown(decode_text(path.read_bytes()))
    return _structure(elements, "markdown")


# ── HTML ─────────────────────────────────────────────────────────────────────

_DROP_TAGS = ["script", "style", "noscript", "template", "svg", "canvas", "iframe", "object",
              "embed", "form", "button", "input", "select", "nav", "header", "footer", "aside"]
_DROP_ROLES = {"navigation", "banner", "contentinfo", "complementary", "search", "dialog"}
_BLOCKS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "table", "pre", "blockquote", "dl"}


def _visible(tag) -> bool:
    style = (tag.get("style") or "").replace(" ", "").lower()
    return not (
        tag.has_attr("hidden")
        or tag.get("aria-hidden") == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


def _text(tag) -> str:
    return " ".join(normalize(tag.get_text(" ", strip=True)).split())


def _own_text(item) -> str:
    """An item's text without its nested lists (they are listed below it)."""
    parts = []
    for piece in item.find_all(string=True):
        ancestor = piece.parent
        nested = False
        while ancestor is not None and ancestor is not item:
            if ancestor.name in ("ul", "ol"):
                nested = True
                break
            ancestor = ancestor.parent
        if not nested:
            parts.append(piece)
    return " ".join(normalize(" ".join(parts)).split())


def _list_lines(tag, depth: int = 0) -> list[str]:
    lines = []
    for item in tag.find_all("li", recursive=False):
        text = _own_text(item)
        if text:
            lines.append(f"{'  ' * depth}- {text}")
        for child in item.find_all(["ul", "ol"], recursive=False):
            lines += _list_lines(child, depth + 1)
    return lines


def _html_table(tag) -> Optional[ExtractedElement]:
    rows = []
    for tr in tag.find_all("tr"):
        cells = [_text(cell) for cell in tr.find_all(["th", "td"])]
        if cells:
            rows.append(cells)
    rows = clean_rows(rows)
    if not rows:
        return None
    first = tag.find("tr")
    has_th_header = first is not None and first.find("th") is not None and not first.find("td")
    header, data = (rows[0], rows[1:]) if has_th_header else split_header(rows)
    return table(header, data)


_CONTAINERS = {"ul", "ol", "table", "pre", "blockquote", "dl"}


def _inside_container(tag, root) -> bool:
    for parent in tag.parents:
        if parent is root:
            return False
        if parent.name in _CONTAINERS:
            return True
    return False


def parse_html(markup: bytes | str) -> tuple[list[ExtractedElement], Optional[str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(markup, "lxml")
    title = _text(soup.title) if soup.title else None
    for tag in soup.find_all(_DROP_TAGS):
        tag.decompose()
    for tag in soup.find_all(attrs={"role": True}):
        if tag.get("role") in _DROP_ROLES:
            tag.decompose()
    for tag in soup.find_all(True):
        if not tag.decomposed and not _visible(tag):
            tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup

    elements: list[ExtractedElement] = []
    for tag in root.find_all(list(_BLOCKS)):
        # Only outermost blocks: a <p> inside a list item or table cell is
        # read as part of that list or table.
        if _inside_container(tag, root):
            continue
        name = tag.name
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            text = _text(tag)
            if text:
                elements.append(heading(text, int(name[1])))
        elif name in {"ul", "ol"}:
            lines = _list_lines(tag)
            if lines:
                elements.append(ExtractedElement("\n".join(lines), "list"))
        elif name == "table":
            element = _html_table(tag)
            if element:
                elements.append(element)
        elif name == "pre":
            code = normalize(tag.get_text()).strip("\n")
            if code.strip():
                elements.append(ExtractedElement(code, "code"))
        else:
            # Inline markup (<b>, <a>, <span>) is part of the sentence.
            text = _text(tag)
            if text:
                elements.append(ExtractedElement(text, "text"))
    # Loose text directly in containers (no <p>), common in older pages.
    if not elements:
        text = clean_block(root.get_text("\n", strip=True))
        elements = [ExtractedElement(paragraph, "text") for paragraph in text.split("\n\n") if paragraph.strip()]
    return elements, title


def extract_html(path: Path) -> DocumentStructure:
    elements, title = parse_html(path.read_bytes())
    structure = _structure(elements, "html")
    if title:
        structure.metadata["title"] = title
    return structure


def _structure(elements: list[ExtractedElement], method: str) -> DocumentStructure:
    if not elements:
        raise ExtractionError("No readable text was found in this file.")
    return DocumentStructure(
        elements=elements, total_pages=0,
        has_tables=any(e.element_type == "table" for e in elements),
        has_images=False, metadata={"extraction_method": method},
    )
