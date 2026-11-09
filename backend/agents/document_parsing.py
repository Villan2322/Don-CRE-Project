"""
Document Parsing Agent

Detects file type, pulls text out of text-based files, and decides when a
file needs OCR (scanned PDFs, images). No LLM calls here.
"""

import csv
import io
from dataclasses import dataclass
from typing import Optional

from pypdf import PdfReader
import openpyxl

try:
    import xlrd  # legacy .xls
except ImportError:  # pragma: no cover
    xlrd = None

# A text PDF averages far more than this per page; scans average near zero.
MIN_CHARS_PER_PAGE = 80
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp")


@dataclass
class ParseResult:
    is_parseable: bool
    file_type: str
    extracted_text: str
    page_count: Optional[int]
    needs_ocr: bool
    method: str
    reason: str


class DocumentParsingAgent:
    def __init__(self):
        self.name = "DocumentParsingAgent"

    def check(self, filename: str, file_content: bytes, content_type: str) -> ParseResult:
        name = filename.lower()
        content_type = content_type or ""
        if name.endswith(".pdf") or content_type == "application/pdf":
            return self._parse_pdf(file_content)
        if name.endswith(".xlsx") or name.endswith(".xlsm"):
            return self._parse_xlsx(file_content)
        if name.endswith(".xls"):
            return self._parse_xls(file_content)
        if name.endswith(".csv") or content_type == "text/csv":
            return self._parse_csv(file_content)
        if name.endswith(".txt") or content_type.startswith("text/"):
            return self._ok("text", self._decode(file_content), 1, "decode")
        if name.endswith(IMAGE_EXTENSIONS) or content_type.startswith("image/"):
            return ParseResult(True, "image", "", 1, True, "ocr_required", "Image needs OCR")
        return ParseResult(False, "unknown", "", None, False, "none",
                           f"Unsupported file type ({content_type or filename.rsplit('.', 1)[-1]})")

    def _parse_pdf(self, content: bytes) -> ParseResult:
        try:
            reader = PdfReader(io.BytesIO(content))
            pages = [page.extract_text() or "" for page in reader.pages]
        except Exception as e:
            return ParseResult(True, "pdf", "", None, True, "ocr_fallback",
                               f"PDF text layer unreadable ({e}); using OCR")
        page_count = len(pages)
        chars = sum(len(p.strip()) for p in pages)
        if page_count == 0 or chars / page_count < MIN_CHARS_PER_PAGE:
            return ParseResult(True, "pdf", "", page_count, True, "ocr_required",
                               "PDF looks scanned (little or no text layer); using OCR")
        text = "\n\n".join(f"=== Page {i + 1} ===\n{p}" for i, p in enumerate(pages))
        return self._ok("pdf", text, page_count, "pypdf")

    def _parse_xlsx(self, content: bytes) -> ParseResult:
        try:
            wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
            parts = []
            for ws in wb.worksheets:
                parts.append(f"=== Sheet: {ws.title} ===")
                for row in ws.iter_rows(values_only=True):
                    line = "\t".join("" if c is None else str(c) for c in row)
                    if line.strip():
                        parts.append(line)
            return self._ok("excel", "\n".join(parts), len(wb.worksheets), "openpyxl")
        except Exception as e:
            return ParseResult(False, "excel", "", None, False, "none", f"Spreadsheet could not be read: {e}")

    def _parse_xls(self, content: bytes) -> ParseResult:
        if xlrd is None:
            return ParseResult(False, "excel", "", None, False, "none",
                               "Legacy .xls files need xlrd; save as .xlsx and re-upload")
        try:
            book = xlrd.open_workbook(file_contents=content)
            parts = []
            for sheet in book.sheets():
                parts.append(f"=== Sheet: {sheet.name} ===")
                for r in range(sheet.nrows):
                    line = "\t".join(str(v) for v in sheet.row_values(r))
                    if line.strip():
                        parts.append(line)
            return self._ok("excel", "\n".join(parts), book.nsheets, "xlrd")
        except Exception as e:
            return ParseResult(False, "excel", "", None, False, "none", f"Spreadsheet could not be read: {e}")

    def _parse_csv(self, content: bytes) -> ParseResult:
        text = self._decode(content)
        rows = csv.reader(io.StringIO(text))
        return self._ok("csv", "\n".join("\t".join(r) for r in rows), 1, "csv")

    @staticmethod
    def _decode(content: bytes) -> str:
        for encoding in ("utf-8-sig", "cp1252"):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode("utf-8", errors="replace")

    @staticmethod
    def _ok(file_type: str, text: str, pages: Optional[int], method: str) -> ParseResult:
        if not text.strip():
            return ParseResult(False, file_type, "", pages, False, method, "File contains no text")
        return ParseResult(True, file_type, text, pages, False, method, "Text extracted")
