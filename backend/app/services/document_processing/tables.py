"""Tables as Markdown, the representation embedders, rerankers and LLMs read best.

Every format parser hands tables over as a header row plus data rows; this
module cleans them and renders them. When a table is too long for one
chunk, each part repeats the header so every chunk stays self-describing.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence

from app.services.document_processing.cleaning import normalize

Row = list[str]


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)  # spreadsheets store 12 as 12.0
    text = normalize(str(value))
    return " ".join(text.split()).replace("|", "\\|")


def clean_rows(rows: Sequence[Sequence[object]]) -> list[Row]:
    """Drop empty rows and columns; collapse horizontally merged duplicates."""
    table = [[cell_text(c) for c in row] for row in rows]
    table = [row for row in table if any(row)]
    if not table:
        return []
    width = max(len(row) for row in table)
    table = [row + [""] * (width - len(row)) for row in table]
    keep = [i for i in range(width) if any(row[i] for row in table)]
    table = [[row[i] for i in keep] for row in table]
    # A cell merged across columns is repeated by most readers; keep one copy.
    deduped = []
    for row in table:
        out: Row = []
        for i, cell in enumerate(row):
            out.append("" if i and cell and cell == row[i - 1] and len(cell) > 3 else cell)
        deduped.append(out)
    return deduped


def split_header(rows: list[Row]) -> tuple[Optional[Row], list[Row]]:
    """Treat the first row as a header when it looks like one.

    A header has no empty cells and is not purely numeric; otherwise the
    table gets generic column names so data is never mistaken for labels.
    """
    if not rows:
        return None, []
    first = rows[0]
    looks_like_header = all(first) and not all(_is_number(c) for c in first) and len(rows) > 1
    if looks_like_header:
        return first, rows[1:]
    return [f"Column {i + 1}" for i in range(len(first))], rows


def to_markdown(header: Row, rows: Sequence[Row]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def split_markdown(
    header: Row,
    rows: Sequence[Row],
    *,
    max_tokens: int,
    count_tokens: Callable[[str], int],
) -> list[str]:
    """Render in parts of at most ``max_tokens``, each with the header."""
    if not rows:
        return [to_markdown(header, [])]
    parts: list[str] = []
    current: list[Row] = []
    for row in rows:
        candidate = to_markdown(header, current + [row])
        if current and count_tokens(candidate) > max_tokens:
            parts.append(to_markdown(header, current))
            current = [row]
        else:
            current.append(row)
    if current:
        parts.append(to_markdown(header, current))
    return parts


def _is_number(text: str) -> bool:
    try:
        float(text.replace(",", "").replace("%", "").strip())
        return True
    except ValueError:
        return False
