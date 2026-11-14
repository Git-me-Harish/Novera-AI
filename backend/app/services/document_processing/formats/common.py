"""Checks every parser runs before trusting a file."""
from __future__ import annotations

import zipfile
from pathlib import Path

from app.services.document_processing.elements import ExtractionError

# Office Open XML files are ZIP archives; a tiny upload can expand to
# gigabytes ("zip bomb"). Refuse before any library inflates it.
MAX_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200

_OOXML_MAIN_PART = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def head(path: Path, size: int = 2048) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(size)


def check_signature(path: Path, ext: str) -> None:
    """The bytes must match the extension; a renamed file is refused."""
    start = head(path)
    if ext == ".pdf" and b"%PDF-" not in start[:1024]:
        raise ExtractionError("This file is not a valid PDF.")
    if ext in (".doc", ".xls") and not start.startswith(_OLE2):
        # Some ".xls" files are really HTML or CSV exports; say so plainly.
        raise ExtractionError(
            f"This {ext} file is not a legacy Office document. Save it as "
            f"{'.docx' if ext == '.doc' else '.xlsx or .csv'} and upload again."
        )
    if ext in _OOXML_MAIN_PART:
        guard_zip(path, _OOXML_MAIN_PART[ext], ext)


def guard_zip(path: Path, main_part: str, ext: str) -> None:
    if not zipfile.is_zipfile(path):
        raise ExtractionError(f"This file is not a valid {ext} document.")
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if main_part not in names:
            raise ExtractionError(f"This file is not a valid {ext} document.")
        total = sum(info.file_size for info in archive.infolist())
        packed = max(1, sum(info.compress_size for info in archive.infolist()))
    if total > MAX_UNCOMPRESSED_BYTES or total / packed > MAX_COMPRESSION_RATIO:
        raise ExtractionError("This file expands to an unsafe size and was not processed.")


def decode_text(data: bytes) -> str:
    """Decode bytes of unknown encoding without silently dropping characters."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    best = from_bytes(data).best()
    if best is None:
        raise ExtractionError("The text encoding of this file could not be detected.")
    return str(best)
