"""
OCR Agent

Reads scanned PDFs and images by sending them straight to Claude, which
reads image-only pages natively. No Tesseract or poppler binaries, so it runs
the same in a slim container as it does locally.

Long scans are split into small batches of pages and read in parallel, so no
single call runs into the output limit and big packages finish faster.
"""

import asyncio
import base64
import io
from typing import Optional

from pypdf import PdfReader, PdfWriter

from .base import BaseAgent, complete, fatal_api_message

TRANSCRIBE_PROMPT = """Transcribe every piece of text in this document exactly as written.
Keep tables as tab-separated rows, one row per line, with the header row first.
If a page is rotated, read it in its upright orientation.
Mark each page with a line like "=== Page {first} ===", numbering pages from {first}.
Do not summarize, interpret, or fix numbers. If something is illegible, write [illegible].
Output the transcription only."""

PAGES_PER_BATCH = 3
PARALLEL_BATCHES = 4
TRANSCRIBE_MAX_TOKENS = 16000
MAX_FILE_BYTES = 30 * 1024 * 1024  # Claude's request ceiling is 32 MB

IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp",
}


class OCRAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="OCRAgent", system_prompt="")

    async def process(self, file_content: bytes, filename: str,
                      page_count: Optional[int] = None) -> dict:
        name = filename.lower()
        if len(file_content) > MAX_FILE_BYTES:
            return self._fail(f"File is {len(file_content) / 1e6:.0f} MB; scanned files must be under 30 MB")
        if name.endswith(".pdf"):
            batches = self._pdf_batches(file_content)
        else:
            media_type = next((t for ext, t in IMAGE_TYPES.items() if name.endswith(ext)), None)
            if media_type is None:
                return self._fail(f"Unsupported file type for OCR: {filename}")
            batches = [(1, 1, {"type": "image", "source": {
                "type": "base64", "media_type": media_type,
                "data": base64.standard_b64encode(file_content).decode("ascii")}})]

        slots = asyncio.Semaphore(PARALLEL_BATCHES)

        async def read(first: int, last: int, block: dict):
            async with slots:
                return await complete(
                    self.client, model=self.model, max_tokens=TRANSCRIBE_MAX_TOKENS,
                    messages=[{"role": "user", "content": [
                        block, {"type": "text", "text": TRANSCRIBE_PROMPT.format(first=first)}]}])

        results = await asyncio.gather(*[read(*b) for b in batches], return_exceptions=True)

        parts, issues = [], []
        for (first, last, _), result in zip(batches, results):
            label = f"page {first}" if first == last else f"pages {first}–{last}"
            if isinstance(result, Exception):
                if fatal_api_message(result):
                    raise result
                issues.append(f"Could not read {label}: {result}")
                continue
            text, stop_reason = result
            if stop_reason == "max_tokens":
                issues.append(f"Transcription of {label} was cut off")
            parts.append(text.strip())

        text = "\n\n".join(p for p in parts if p)
        illegible = text.count("[illegible]")
        if illegible:
            issues.append(f"{illegible} illegible passage(s)")
        readable = len(text) > 50
        return {
            "document_readable": readable,
            "cleaned_text": text,
            "confidence": None,
            "ocr_issues_found": issues if readable else issues + ["No readable text found"],
            "pages_processed": page_count or len(batches),
        }

    @staticmethod
    def _pdf_batches(content: bytes) -> list[tuple[int, int, dict]]:
        """Split a PDF into small PDFs of a few pages each. Falls back to the whole file."""
        def block(data: bytes) -> dict:
            return {"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(data).decode("ascii")}}
        try:
            reader = PdfReader(io.BytesIO(content))
            total = len(reader.pages)
            batches = []
            for start in range(0, total, PAGES_PER_BATCH):
                writer = PdfWriter()
                for i in range(start, min(start + PAGES_PER_BATCH, total)):
                    writer.add_page(reader.pages[i])
                buf = io.BytesIO()
                writer.write(buf)
                batches.append((start + 1, min(start + PAGES_PER_BATCH, total), block(buf.getvalue())))
            if batches:
                return batches
        except Exception:
            pass  # unreadable structure (e.g. encrypted) — let Claude take the whole file
        return [(1, 1, block(content))]

    @staticmethod
    def _fail(reason: str) -> dict:
        return {"document_readable": False, "cleaned_text": "", "confidence": None,
                "ocr_issues_found": [reason], "pages_processed": 0}
