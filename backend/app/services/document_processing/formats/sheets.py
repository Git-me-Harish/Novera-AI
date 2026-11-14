"""Spreadsheets (.xlsx, .xls) and CSV.

Each visible sheet becomes a section (its name) holding one table: empty
rows and columns removed, the header row detected, dates written as dates
and whole numbers without ".0". The chunker splits long tables and repeats
the header in every part, so each chunk can be read on its own.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, time
from pathlib import Path

from app.services.document_processing.elements import (
    DocumentStructure,
    ExtractedElement,
    ExtractionError,
    heading,
    table,
)
from app.services.document_processing.formats.common import decode_text
from app.services.document_processing.tables import clean_rows, split_header

MAX_ROWS_PER_SHEET = 50_000


def _cell(value):
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time() else value.isoformat(sep=" ", timespec="minutes")
    if isinstance(value, date):
        return value.isoformat()
    return value


def _sheet_elements(name: str, raw_rows: list, sheet_number: int) -> list[ExtractedElement]:
    if len(raw_rows) > MAX_ROWS_PER_SHEET:
        raise ExtractionError(
            f"Sheet '{name}' has more than {MAX_ROWS_PER_SHEET:,} rows. Split it or export the part you need."
        )
    rows = clean_rows([[_cell(v) for v in row] for row in raw_rows])
    if not rows:
        return []
    header, data = split_header(rows)
    return [heading(name, 1), table(header, data, None, sheet=name, sheet_index=sheet_number)]


def _structure(elements: list[ExtractedElement], sheets: int, method: str) -> DocumentStructure:
    if not any(e.element_type == "table" for e in elements):
        raise ExtractionError("This spreadsheet has no data.")
    return DocumentStructure(
        elements=elements, total_pages=0, has_tables=True, has_images=False,
        metadata={"extraction_method": method, "sheets": sheets},
    )


def extract_xlsx(path: Path) -> DocumentStructure:
    import openpyxl

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:
        raise ExtractionError("This Excel file could not be opened; it may be damaged.") from exc
    elements: list[ExtractedElement] = []
    try:
        for index, sheet in enumerate(workbook.worksheets, start=1):
            # Hidden sheets are usually lookups and helper data, not content.
            if sheet.sheet_state != "visible":
                continue
            elements += _sheet_elements(sheet.title, list(sheet.iter_rows(values_only=True)), index)
    finally:
        workbook.close()
    return _structure(elements, len(workbook.sheetnames), "xlsx")


def extract_xls(path: Path) -> DocumentStructure:
    import xlrd

    try:
        book = xlrd.open_workbook(path, on_demand=True)
    except Exception as exc:
        raise ExtractionError("This .xls file could not be opened; it may be damaged.") from exc
    elements: list[ExtractedElement] = []
    try:
        for index in range(book.nsheets):
            sheet = book.sheet_by_index(index)
            if getattr(sheet, "visibility", 0) != 0:
                continue
            rows = []
            for r in range(sheet.nrows):
                row = []
                for c in range(sheet.ncols):
                    cell = sheet.cell(r, c)
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        row.append(xlrd.xldate_as_datetime(cell.value, book.datemode))
                    else:
                        row.append(cell.value)
                rows.append(row)
            elements += _sheet_elements(sheet.name, rows, index + 1)
    finally:
        book.release_resources()
    return _structure(elements, book.nsheets, "xls")


def extract_csv(path: Path) -> DocumentStructure:
    text = decode_text(path.read_bytes())
    sample = text[:20_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    elements = _sheet_elements(path.stem, rows, 1)
    if elements:
        elements = elements[1:]  # the file name is already the document title
    return _structure(elements, 1, "csv")
