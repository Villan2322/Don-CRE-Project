"""
OCR Agent

Reads scanned PDFs and images by sending the file straight to Claude,
which handles image-only pages natively. No Tesseract or poppler binaries,
so it runs the same on Vercel as it does locally.
"""

import base64
from typing import Optional

from .base import BaseAgent

TRANSCRIBE_PROMPT = """Transcribe every piece of text in this document exactly as written.
Keep tables as tab-separated rows, one row per line, with the header row first.
Mark each page with a line like "=== Page 3 ===".
Do not summarize, interpret, or fix numbers. If something is illegible, write [illegible].
Output the transcription only."""

TRANSCRIBE_MAX_TOKENS = 20000
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
        block = self._content_block(file_content, filename)
        if block is None:
            return self._fail(f"Unsupported file type for OCR: {filename}")
        if len(file_content) > MAX_FILE_BYTES:
            return self._fail(f"File is {len(file_content) / 1e6:.0f} MB; scanned files must be under 30 MB")

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=TRANSCRIBE_MAX_TOKENS,
                temperature=0,
                messages=[{"role": "user", "content": [block, {"type": "text", "text": TRANSCRIBE_PROMPT}]}],
            )
        except Exception as e:
            return self._fail(f"OCR request failed: {e}")

        text = "".join(b.text for b in response.content if b.type == "text").strip()
        issues = []
        if response.stop_reason == "max_tokens":
            issues.append("Transcription was cut off — document is very long; later pages may be missing")
        illegible = text.count("[illegible]")
        if illegible:
            issues.append(f"{illegible} illegible passage(s)")

        readable = len(text) > 50
        return {
            "document_readable": readable,
            "cleaned_text": text,
            "confidence": None,
            "ocr_issues_found": issues if readable else issues + ["No readable text found"],
            "pages_processed": page_count,
        }

    def _content_block(self, file_content: bytes, filename: str) -> Optional[dict]:
        name = filename.lower()
        data = base64.standard_b64encode(file_content).decode("ascii")
        if name.endswith(".pdf"):
            return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
        for ext, media_type in IMAGE_TYPES.items():
            if name.endswith(ext):
                return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
        return None

    @staticmethod
    def _fail(reason: str) -> dict:
        return {"document_readable": False, "cleaned_text": "", "confidence": None,
                "ocr_issues_found": [reason], "pages_processed": 0}
