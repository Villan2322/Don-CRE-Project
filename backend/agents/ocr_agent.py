import io
from typing import Optional
from .base import BaseAgent

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except ImportError:
    FITZ_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


OCR_CLEANUP_PROMPT = """You are an expert document text cleaning agent for commercial real estate documents.

You will receive raw OCR text extracted from a scanned document. The text may contain:
- Garbled characters or symbols from poor scan quality
- Misrecognized numbers (0/O confusion, 1/l confusion, etc.)
- Broken words split across lines incorrectly
- Random whitespace, header/footer noise, page numbers mixed into content
- Tables rendered as misaligned rows

Your job:
1. Clean and correct the OCR text to make it accurately readable
2. Preserve all factual data exactly — tenant names, dollar amounts, square footage, dates
3. Reconstruct table structures where possible using pipe-delimited plain text
4. Flag unreadable sections with [UNREADABLE SECTION]
5. Rate your confidence in the cleaned output

Return JSON only:
{
  "cleaned_text": "<fully cleaned, readable document text>",
  "confidence": 0.87,
  "ocr_issues_found": ["misaligned table on page 2"],
  "unreadable_sections": ["page 3 footer"],
  "document_readable": true
}"""


class OCRAgent(BaseAgent):
    """
    Handles scanned/image-based PDFs that cannot be read as text-native.

    Pipeline:
      1. Render each PDF page to an image via PyMuPDF
      2. Run Tesseract OCR to extract raw text from each image
      3. Pass raw OCR text through LLM to clean, correct, and restructure
      4. Return cleaned text + metadata for downstream agents
    """

    def __init__(self):
        super().__init__(
            name="OCRAgent",
            system_prompt=OCR_CLEANUP_PROMPT,
        )

    async def process(
        self,
        file_content: bytes,
        filename: str,
        page_count: Optional[int] = None,
    ) -> dict:
        """
        Run OCR on a scanned PDF and clean the output via LLM.
        """
        raw_text, method = self._run_ocr(file_content, filename)

        if not raw_text.strip():
            return {
                "raw_ocr_text": "",
                "cleaned_text": "",
                "confidence": 0.0,
                "ocr_issues_found": ["No text could be extracted via OCR"],
                "unreadable_sections": ["entire document"],
                "document_readable": False,
                "method": method,
            }

        # Clean via LLM — chunk if too long
        if len(raw_text) <= 15000:
            cleaned_result = await self.analyze(raw_text[:15000])
        else:
            cleaned_result = await self._process_in_chunks(raw_text)

        return {
            "raw_ocr_text": raw_text,
            "cleaned_text": cleaned_result.get("cleaned_text", raw_text),
            "confidence": cleaned_result.get("confidence", 0.5),
            "ocr_issues_found": cleaned_result.get("ocr_issues_found", []),
            "unreadable_sections": cleaned_result.get("unreadable_sections", []),
            "document_readable": cleaned_result.get("document_readable", True),
            "method": method,
        }

    def _run_ocr(self, file_content: bytes, filename: str) -> tuple:
        if FITZ_AVAILABLE and TESSERACT_AVAILABLE:
            try:
                return self._ocr_with_pymupdf_tesseract(file_content), "pymupdf+tesseract"
            except Exception:
                pass

        if FITZ_AVAILABLE:
            try:
                doc = fitz.open(stream=file_content, filetype="pdf")
                texts = [page.get_text() for page in doc]
                doc.close()
                combined = "\n".join(texts)
                if combined.strip():
                    return combined, "pymupdf-text-fallback"
            except Exception:
                pass

        return (
            "[OCR unavailable — ensure tesseract-ocr is installed and pytesseract/pymupdf are in dependencies]",
            "unavailable",
        )

    def _ocr_with_pymupdf_tesseract(self, file_content: bytes) -> str:
        doc = fitz.open(stream=file_content, filetype="pdf")
        all_text = []
        for page_num, page in enumerate(doc):
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            page_text = pytesseract.image_to_string(img, lang="eng")
            all_text.append(f"--- Page {page_num + 1} ---\n{page_text}")
        doc.close()
        return "\n\n".join(all_text)

    async def _process_in_chunks(self, raw_text: str, chunk_size: int = 12000) -> dict:
        chunks = [raw_text[i:i + chunk_size] for i in range(0, len(raw_text), chunk_size)]
        cleaned_parts = []
        all_issues = []
        all_unreadable = []
        min_confidence = 1.0

        for chunk in chunks:
            result = await self.analyze(chunk)
            cleaned_parts.append(result.get("cleaned_text", chunk))
            all_issues.extend(result.get("ocr_issues_found", []))
            all_unreadable.extend(result.get("unreadable_sections", []))
            min_confidence = min(min_confidence, result.get("confidence", 0.5))

        return {
            "cleaned_text": "\n\n".join(cleaned_parts),
            "confidence": min_confidence,
            "ocr_issues_found": all_issues,
            "unreadable_sections": all_unreadable,
            "document_readable": len(all_unreadable) < len(chunks),
        }
