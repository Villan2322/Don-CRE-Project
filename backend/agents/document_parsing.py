import io
from typing import Optional

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


# Minimum avg chars per page to consider a PDF text-native (not scanned)
TEXT_DENSITY_THRESHOLD = 50


class ParseabilityResult:
    """Result from the document parsing check."""

    def __init__(self, is_parseable, needs_ocr, file_type, method,
                 extracted_text, page_count, reason, confidence):
        self.is_parseable = is_parseable
        self.needs_ocr = needs_ocr
        self.file_type = file_type
        self.method = method
        self.extracted_text = extracted_text
        self.page_count = page_count
        self.reason = reason
        self.confidence = confidence

    def to_dict(self):
        return {
            "is_parseable": self.is_parseable,
            "needs_ocr": self.needs_ocr,
            "file_type": self.file_type,
            "method": self.method,
            "page_count": self.page_count,
            "reason": self.reason,
            "confidence": self.confidence,
            "text_length": len(self.extracted_text),
        }


class DocumentParsingAgent:
    """
    First agent in the pipeline. Determines whether a document is directly
    parseable (text-native PDF or Excel) or requires OCR (scanned/image PDF).
    """

    def check(self, filename, file_content, content_type):
        lower = filename.lower()

        # Excel
        if lower.endswith((".xlsx", ".xls")) or content_type in (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel",
        ):
            text = self._extract_excel(file_content)
            return ParseabilityResult(True, False, "excel", "openpyxl",
                                      text, None, "Excel file extracted directly", 1.0)

        # CSV
        if lower.endswith(".csv"):
            text = file_content.decode("utf-8", errors="ignore")
            return ParseabilityResult(True, False, "csv", "utf-8-decode",
                                      text, None, "CSV file decoded directly", 1.0)

        # PDF
        if lower.endswith(".pdf") or content_type == "application/pdf":
            return self._check_pdf(file_content)

        # Plain text fallback
        try:
            text = file_content.decode("utf-8", errors="ignore")
            if len(text.strip()) > 20:
                return ParseabilityResult(True, False, "text", "utf-8-decode",
                                          text, None, "Plain text file", 0.9)
        except Exception:
            pass

        return ParseabilityResult(False, False, "unknown", "none", "",
                                  None, f"Unsupported file type: {filename}", 0.0)

    def _check_pdf(self, file_content):
        if not FITZ_AVAILABLE:
            return self._check_pdf_pypdf2(file_content)
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            page_count = len(doc)
            total_chars = 0
            parts = []
            for page in doc:
                text = page.get_text()
                total_chars += len(text.strip())
                parts.append(text)
            doc.close()
            avg = total_chars / max(page_count, 1)
            if avg >= TEXT_DENSITY_THRESHOLD:
                return ParseabilityResult(True, False, "pdf", "pymupdf-text",
                                          "\n".join(parts), page_count,
                                          f"Text-native PDF ({avg:.0f} chars/page)", 0.95)
            else:
                return ParseabilityResult(True, True, "pdf", "ocr-required",
                                          "", page_count,
                                          f"Scanned PDF — {avg:.0f} chars/page avg, OCR required", 0.9)
        except Exception as e:
            return ParseabilityResult(False, False, "pdf", "none", "",
                                      None, f"PDF could not be opened: {e}", 0.0)

    def _check_pdf_pypdf2(self, file_content):
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(io.BytesIO(file_content))
            page_count = len(reader.pages)
            total_chars = 0
            parts = []
            for page in reader.pages:
                text = page.extract_text() or ""
                total_chars += len(text.strip())
                parts.append(text)
            avg = total_chars / max(page_count, 1)
            if avg >= TEXT_DENSITY_THRESHOLD:
                return ParseabilityResult(True, False, "pdf", "pypdf2-text",
                                          "\n".join(parts), page_count,
                                          f"Text-native PDF ({avg:.0f} chars/page)", 0.85)
            else:
                return ParseabilityResult(True, True, "pdf", "ocr-required",
                                          "", page_count,
                                          f"Scanned PDF — {avg:.0f} chars/page, OCR required", 0.8)
        except Exception as e:
            return ParseabilityResult(False, False, "pdf", "none", "",
                                      None, f"PDF could not be read: {e}", 0.0)

    def _extract_excel(self, file_content):
        if not OPENPYXL_AVAILABLE:
            return "[Excel parsing not available]"
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_content), data_only=True)
            sheets = []
            for name in wb.sheetnames:
                ws = wb[name]
                rows = ["\t".join(str(c) if c is not None else "" for c in row)
                        for row in ws.iter_rows(values_only=True)]
                sheets.append(f"=== Sheet: {name} ===\n" + "\n".join(rows))
            return "\n\n".join(sheets)
        except Exception as e:
            return f"[Error extracting Excel data: {e}]"
