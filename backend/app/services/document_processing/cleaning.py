"""Text normalisation shared by every format parser.

Noise that reaches the index costs twice: it dilutes embeddings and it
spends the generator's context budget. Everything here is conservative —
it removes rendering artefacts, never words.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable

# Private-use and decorative glyphs that PDF fonts emit for bullets.
_BULLETS = "•●▪■‣⁃∙◦○–—"
_BULLET_LINE = re.compile(rf"^\s*[{re.escape(_BULLETS)}\-\*]\s*$")
_LEADING_BULLET = re.compile(rf"^\s*[{re.escape(_BULLETS)}]\s*")
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿­]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Decorated page numbers only ("Page 3", "3 of 12", "- 3 -"). A bare number
# can be data ("24" bolded in a sentence); bare page numbers at page edges
# are removed by repeating_lines instead.
_PAGE_NUMBER = re.compile(
    r"^\s*(?:page\s*\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?|\d{1,4}\s*(?:of|/)\s*\d{1,4}|[-–—]\s*\d{1,4}\s*[-–—])\s*$",
    re.IGNORECASE,
)
_TOC_LINE = re.compile(r"^.{3,}?(?:\s*\.{4,}|\s{2,}\.{2,}|…{2,})\s*\d{1,4}\s*$")
_HYPHEN_BREAK = re.compile(r"(\w)-\n(\w)")
_MULTI_SPACE = re.compile(r"[ \t ]+")


def normalize(text: str) -> str:
    """Unicode-normalise and strip invisible or control characters.

    NFKC folds ligatures (ﬁ → fi) and full-width forms so the same word
    always tokenises the same way for keyword search and embeddings.
    """
    text = unicodedata.normalize("NFKC", text or "")
    text = _ZERO_WIDTH.sub("", text)
    text = _CONTROL.sub("", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def tidy_line(line: str) -> str:
    """Collapse runs of spaces and turn decorative bullets into '- '."""
    line = _MULTI_SPACE.sub(" ", line).strip()
    if _LEADING_BULLET.match(line):
        line = "- " + _LEADING_BULLET.sub("", line)
    return line


def _join_hyphen(match: re.Match) -> str:
    left, right = match.group(1), match.group(2)
    return left + right if right.islower() else f"{left}-{right}"


def is_noise_line(line: str) -> bool:
    """Page numbers, table-of-contents leaders and lone bullet glyphs."""
    stripped = line.strip()
    return (
        not stripped
        or bool(_PAGE_NUMBER.match(stripped))
        or bool(_TOC_LINE.match(stripped))
        or bool(_BULLET_LINE.match(stripped))
    )


def join_wrapped_lines(lines: Iterable[str]) -> str:
    """Rebuild a paragraph from layout lines.

    Hyphenation at a line break is undone only when a lowercase letter
    follows ("manage-\\nment"), so "COVID-\\n19" and "e-\\nKYC" survive.
    Lines that start a list item keep their own line.
    """
    out: list[str] = []
    for raw in lines:
        line = tidy_line(raw)
        if not line:
            continue
        if out and not line.startswith("- ") and not re.match(r"^\d+[.)]\s", line):
            previous = out[-1]
            if previous.endswith("-") and previous[-2:-1].isalnum():
                # "manage-/ment" -> "management"; "e-/KYC" -> "e-KYC".
                out[-1] = (previous[:-1] if line[:1].islower() else previous) + line
                continue
            out[-1] = f"{previous} {line}"
        else:
            out.append(line)
    return "\n".join(out)


def clean_block(text: str) -> str:
    """Normalise a block that already has meaningful line breaks."""
    text = normalize(text)
    text = _HYPHEN_BREAK.sub(_join_hyphen, text)
    lines = [tidy_line(line) for line in text.split("\n")]
    kept = [line for line in lines if not is_noise_line(line)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


def repeating_lines(pages: list[list[str]], *, edge: int = 2, threshold: float = 0.5) -> set[str]:
    """Running headers and footers: lines that open or close most pages.

    Digits are masked so "Page 3 of 40" and "Page 4 of 40" count as the same
    line. Only the first and last ``edge`` lines of each page are considered,
    so body sentences that merely repeat are never removed.
    """
    if len(pages) < 3:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        candidates = {_mask(line) for line in lines[:edge] + lines[-edge:] if line.strip()}
        counts.update(candidates)
    minimum = max(3, int(len(pages) * threshold))
    return {masked for masked, count in counts.items() if count >= minimum}


def is_repeating(line: str, repeating: set[str]) -> bool:
    return bool(repeating) and _mask(line) in repeating


def _mask(line: str) -> str:
    return re.sub(r"\d+", "#", _MULTI_SPACE.sub(" ", line).strip().casefold())
