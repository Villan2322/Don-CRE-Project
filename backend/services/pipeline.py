"""
CRE Document Intelligence Pipeline - Adaptive Document Processing

Fully adaptive pipeline:
1. Upload ANY document(s) - PDF, Excel, image
2. Auto-detects file type, runs OCR when needed
3. AI-classifies document type
4. Extracts structured data per doc type
5. Synthesizes cross-document analysis with RSF discrepancy detection
6. Returns report with tenants, red flags, score, and recovery opportunity
"""

import asyncio
import json
import re
import os
import base64
from datetime import datetime
from typing import Any
from openai import AsyncOpenAI
import io

from config.extraction_prompts import (
    EXTRACTION_PROMPTS,
    CLASSIFICATION_PROMPT,
    DOC_TYPES,
)
from models.schemas import (
    DealAnalysis,
    LeaseAbstractPipeline as LeaseAbstract,
    TenantInfo,
    RSFReconciliationPipeline as RSFReconciliation,
    RedFlag,
    Severity,
)


class PipelineTracer:
    def __init__(self):
        self.logs = []

    def log(self, stage: str, message: str, level: str = "info", data: dict = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "message": message,
            "level": level,
        }
        if data:
            entry["data"] = data
        self.logs.append(entry)

    def get_logs(self) -> list[dict]:
        return self.logs


class CREPipeline:
    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""),
        )
        self.model = "anthropic/claude-sonnet-4"
        self.tracer = None

    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================

    async def analyze(
        self,
        files: list[dict],
        deal_name: str = None,
        property_appraiser_sf: float = None,
    ) -> dict:
        if not deal_name:
            deal_name = f"Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        self.tracer = PipelineTracer()
        self.tracer.log("START", f"Beginning analysis: {deal_name}", "info", {
            "file_count": len(files),
            "filenames": [f.get("filename", "unknown") for f in files],
        })

        self._property_appraiser_sf = property_appraiser_sf
        if property_appraiser_sf:
            self.tracer.log("BASELINE", f"Property Appraiser SF: {property_appraiser_sf:,.0f} SF", "info")
        else:
            self.tracer.log("BASELINE", "No PA SF provided — comparing across documents only", "warning")

        # Stage 1: Ingest
        self.tracer.log("STAGE_1", "Ingesting files...", "info")
        documents = await self._ingest_files(files)
        if not documents:
            return {
                "success": False,
                "deal_name": deal_name,
                "error": "No processable documents found",
                "trace_log": self.tracer.get_logs(),
            }
        self.tracer.log("STAGE_1", f"Ingested {len(documents)} document(s)", "success")

        # Stage 2: Classify
        self.tracer.log("STAGE_2", "Classifying documents...", "info")
        documents = await self._classify_all(documents)
        for doc in documents:
            self.tracer.log("CLASSIFY", f"{doc.get('filename')} -> {doc.get('doc_type')} ({doc.get('confidence', 0)*100:.0f}%)", "info")

        # Stage 3: Extract
        self.tracer.log("STAGE_3", "Extracting structured data...", "info")
        documents = await self._extract_all(documents)
        self.tracer.log("STAGE_3", f"Extracted from {len(documents)} document(s)", "success")

        # Stage 4: Synthesize
        self.tracer.log("STAGE_4", "Synthesizing analysis...", "info")
        synthesis = await self._synthesize(deal_name, documents)
        self.tracer.log("STAGE_4", "Synthesis complete", "success")

        # Stage 5: Build report
        self.tracer.log("STAGE_5", "Building final report...", "info")
        report = self._build_report(deal_name, documents, synthesis)

        if report.get("rsf_recovery_sf", 0) > 0:
            self.tracer.log("RSF_ALERT", f"Discrepancy: {report['rsf_recovery_sf']:,.0f} SF / ${report.get('rsf_recovery_annual_value', 0):,.0f}/yr recovery", "warning")
        else:
            self.tracer.log("RSF", "No significant RSF discrepancies detected", "success")

        score = report.get("score", 0)
        tier = report.get("tier", "UNKNOWN")
        self.tracer.log("SCORE", f"Deal Score: {score} ({tier})", "success" if tier == "GREEN" else "error" if tier == "RED" else "warning")
        self.tracer.log("COMPLETE", "Analysis complete!", "success")

        report["trace_log"] = self.tracer.get_logs()
        return report

    # Alias for backwards compatibility
    async def run(self, deal_name: str, documents: list[dict]) -> DealAnalysis:
        result = await self.analyze(documents, deal_name)
        return self._to_deal_analysis(result)

    # =========================================================================
    # STAGE 1: Ingest
    # =========================================================================

    async def _ingest_files(self, files: list[dict]) -> list[dict]:
        documents = []
        for i, file in enumerate(files):
            filename = file.get("filename", f"document_{i}")
            content = file.get("content", "")
            content_type = file.get("content_type", self._guess_content_type(filename))

            self.tracer.log("INGEST", f"Processing: {filename}", "info")

            doc = {
                "id": f"doc_{i}",
                "filename": filename,
                "content_type": content_type,
                "file_ext": self._get_ext(filename),
                "ingested_at": datetime.utcnow().isoformat(),
                "extraction_method": None,
                "extraction_errors": [],
            }

            text = ""
            if self._is_excel(filename, content_type):
                text, ok = await self._try_extract_excel(content, filename, doc)
            elif self._is_pdf(filename, content_type):
                text, ok = await self._try_extract_pdf(content, filename, doc)
            elif self._is_image(filename, content_type):
                text, ok = await self._try_ocr(content, filename, doc)
            else:
                if isinstance(content, bytes):
                    try:
                        text = content.decode("utf-8")
                        doc["extraction_method"] = "text_decode"
                    except Exception:
                        text = str(content)
                        doc["extraction_method"] = "text_fallback"
                else:
                    text = str(content) if content else ""
                    doc["extraction_method"] = "text_direct"

            doc["text"] = text
            doc["char_count"] = len(text) if text else 0

            if text and len(text.strip()) > 20:
                documents.append(doc)
                self.tracer.log("INGEST", f"  -> {doc['extraction_method']}: {len(text):,} chars", "success")
            else:
                doc["text"] = f"[EXTRACTION FAILED: {filename}]\n" + "\n".join(doc["extraction_errors"])
                documents.append(doc)
                self.tracer.log("INGEST", f"  -> Minimal content ({len(text)} chars)", "warning")

        return documents

    async def _try_extract_pdf(self, content: bytes | str, filename: str, doc: dict) -> tuple[str, bool]:
        # Method 1: PyPDF2 (fast, text-based PDFs)
        text = self._extract_pdf_text(content)
        has_error = text and "[PDF extraction error" in text

        if not has_error and text and len(text.strip()) > 100:
            doc["extraction_method"] = "pdf_text"
            return text, True

        if has_error:
            doc["extraction_errors"].append(text)

        sparse_chars = len(text.strip()) if text else 0
        self.tracer.log("INGEST", f"  -> Sparse text ({sparse_chars} chars), trying AI OCR...", "info")

        # Method 2: OpenRouter Mistral OCR (scanned PDFs)
        ocr_text = await self._parse_pdf_with_openrouter(content, filename)
        ocr_ok = ocr_text and "[PDF parsing error" not in ocr_text and "[PDF OCR" not in ocr_text

        if ocr_ok and len(ocr_text.strip()) > 50:
            doc["extraction_method"] = "pdf_ai_ocr"
            return ocr_text, True

        if not ocr_ok and ocr_text:
            doc["extraction_errors"].append(f"AI OCR: {ocr_text[:200]}")
            self.tracer.log("INGEST", f"  -> AI OCR failed: {ocr_text[:120]}", "error")

        # Method 3: Combine both if both got partial content
        real_text = text.strip() if text and len(text.strip()) > 20 and not has_error else ""
        real_ocr = ocr_text.strip() if ocr_ok and ocr_text and len(ocr_text.strip()) > 20 else ""
        combined = "\n\n".join(filter(None, [real_text, real_ocr]))
        if combined and len(combined) > 50:
            doc["extraction_method"] = "pdf_combined"
            return combined, True

        # Method 4: Use whatever PyPDF2 got, even if sparse
        if text and len(text.strip()) > 10 and not has_error:
            doc["extraction_method"] = "pdf_raw_fallback"
            self.tracer.log("INGEST", f"  -> Using raw sparse text ({len(text.strip())} chars)", "warning")
            return text, True

        doc["extraction_method"] = "pdf_failed"
        self.tracer.log("INGEST", f"  -> All PDF methods failed for {filename}", "error")
        return f"[PDF EXTRACTION FAILED: {filename}]\n" + "\n".join(doc["extraction_errors"]), True

    async def _parse_pdf_with_openrouter(self, content: bytes | str, filename: str) -> str:
        """Send PDF to OpenRouter with Mistral OCR for scanned document support."""
        try:
            import httpx

            if isinstance(content, bytes):
                b64 = base64.b64encode(content).decode("utf-8")
            else:
                b64 = content

            data_url = f"data:application/pdf;base64,{b64}"

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 8000,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": (
                                        "Extract ALL text from this commercial real estate PDF. "
                                        "Preserve table structure using | column | separators. "
                                        "For rent rolls include: Tenant | Suite | SF | Monthly Rent | Annual Rent | Lease Start | Lease End. "
                                        "Return ONLY the extracted text, no commentary."
                                    )
                                },
                                {
                                    "type": "file",
                                    "file": {"filename": filename, "file_data": data_url}
                                }
                            ]
                        }],
                        "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}]
                    }
                )

                if resp.status_code != 200:
                    return f"[PDF parsing error: HTTP {resp.status_code} - {resp.text[:200]}]"

                data = resp.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]
                return "[PDF parsing error: No content in response]"

        except Exception as e:
            return f"[PDF parsing error: {e}]"

    async def _try_extract_excel(self, content: bytes | str, filename: str, doc: dict) -> tuple[str, bool]:
        text = await self._extract_excel_text(content, filename)
        if text and "[Excel extraction error" not in text:
            doc["extraction_method"] = "excel"
            return text, True
        doc["extraction_errors"].append(text or "Excel extraction failed")
        return "", False

    async def _try_ocr(self, content: bytes | str, filename: str, doc: dict) -> tuple[str, bool]:
        text = await self._ocr_document(content, filename)
        if text and "[OCR error" not in text and len(text.strip()) > 20:
            doc["extraction_method"] = "ocr"
            return text, True
        if text and "[OCR error" in text:
            doc["extraction_errors"].append(text)
        return text or "", False

    def _guess_content_type(self, filename: str) -> str:
        ext = self._get_ext(filename)
        return {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xls": "application/vnd.ms-excel",
            "csv": "text/csv",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "tiff": "image/tiff",
            "tif": "image/tiff",
        }.get(ext, "application/octet-stream")

    def _get_ext(self, filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    def _is_excel(self, fn: str, ct: str) -> bool:
        return self._get_ext(fn) in ["xlsx", "xls", "csv"] or "spreadsheet" in ct or "excel" in ct

    def _is_pdf(self, fn: str, ct: str) -> bool:
        return self._get_ext(fn) == "pdf" or ct == "application/pdf"

    def _is_image(self, fn: str, ct: str) -> bool:
        return self._get_ext(fn) in ["png", "jpg", "jpeg", "tiff", "tif"] or ct.startswith("image/")

    def _extract_pdf_text(self, content: str | bytes) -> str:
        try:
            from PyPDF2 import PdfReader
            from PyPDF2.errors import PdfReadError

            if isinstance(content, str):
                try:
                    content = base64.b64decode(content)
                except Exception:
                    return content
            if not isinstance(content, bytes):
                return "[PDF extraction error: Invalid content]"

            try:
                pdf = PdfReader(io.BytesIO(content))
            except PdfReadError as e:
                if "encrypt" in str(e).lower():
                    return "[PDF extraction error: PDF is encrypted/password-protected]"
                return f"[PDF extraction error: {e}]"

            parts = []
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                try:
                    t = page.extract_text()
                    if t and t.strip():
                        parts.append(f"--- Page {i+1}/{total} ---\n{t.replace(chr(0), '')}")
                except Exception as pe:
                    parts.append(f"--- Page {i+1}/{total} ---\n[Page failed: {pe}]")

            if not parts:
                return "[PDF extraction error: No text found — may be scanned/image-based]"
            return "\n\n".join(parts)

        except ImportError:
            return "[PDF extraction error: PyPDF2 not installed]"
        except Exception as e:
            return f"[PDF extraction error: {e}]"

    async def _extract_excel_text(self, content: str | bytes, filename: str) -> str:
        try:
            import pandas as pd
            if isinstance(content, str):
                try:
                    content = base64.b64decode(content)
                except Exception:
                    return content
            ef = pd.ExcelFile(io.BytesIO(content))
            parts = []
            for sheet in ef.sheet_names:
                df = pd.read_excel(ef, sheet_name=sheet)
                parts.append(f"=== Sheet: {sheet} ===\n{df.to_string()}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"[Excel extraction error: {e}]"

    async def _ocr_document(self, content: str | bytes, filename: str) -> str:
        ext = self._get_ext(filename)
        if ext == "pdf":
            return await self._parse_pdf_with_openrouter(content, filename)

        try:
            import httpx
            if isinstance(content, bytes):
                b64 = base64.b64encode(content).decode("utf-8")
            else:
                b64 = content

            media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                          "tiff": "image/tiff", "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
            raw = content if isinstance(content, bytes) else base64.b64decode(content)
            if len(raw) > 10 * 1024 * 1024:
                return f"[OCR error: Image too large ({len(raw)/1024/1024:.1f}MB)]"

            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 8000,
                        "messages": [{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Extract ALL text from this CRE document image. Preserve table structure with | separators. Return only the extracted text."},
                                {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}}
                            ]
                        }]
                    }
                )
                if resp.status_code != 200:
                    return f"[OCR error: HTTP {resp.status_code} - {resp.text[:200]}]"
                data = resp.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]
                return "[OCR error: No content in response]"
        except Exception as e:
            return f"[OCR error: {e}]"

    # =========================================================================
    # STAGE 2: Classification
    # =========================================================================

    async def _classify_all(self, documents: list[dict]) -> list[dict]:
        tasks = [self._classify_one(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                doc["doc_type"] = "UNKNOWN"
                doc["classification_error"] = str(result)
            else:
                doc.update(result)
        return documents

    async def _classify_one(self, doc: dict) -> dict:
        text = doc.get("text", "")
        # Use beginning + end for classification — avoids sending huge texts
        sample = text[:2000]
        if len(text) > 4000:
            sample += "\n\n[...middle truncated...]\n\n" + text[-2000:]

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"Filename: {doc.get('filename', 'unknown')}\n\nDocument text:\n{sample}"},
            ],
        )

        result = self._parse_json(response.choices[0].message.content)

        # Handle both field name variants
        doc_type = (
            result.get("doc_type")
            or result.get("document_type")
            or result.get("type")
            or "UNKNOWN"
        )
        doc_type = doc_type.upper().strip()

        known = {"LEASE", "LEASE_ABSTRACT", "RENT_ROLL", "RENT_ROLL_XLSX",
                 "BOMA", "FINANCIAL_MODEL", "CAM_RECONCILIATION", "MANAGEMENT_REPORT", "COUNTY_PA"}
        if doc_type not in known:
            normalized = doc_type.replace(" ", "_")
            doc_type = normalized if normalized in known else "UNKNOWN"

        return {
            "doc_type": doc_type,
            "confidence": float(result.get("confidence", 0.5)),
            "reasoning": result.get("reasoning", ""),
        }

    # =========================================================================
    # STAGE 3: Extraction
    # =========================================================================

    async def _extract_all(self, documents: list[dict]) -> list[dict]:
        tasks = [self._extract_one(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                doc["extraction"] = {"error": str(result)}
            else:
                doc["extraction"] = result
            if doc.get("doc_type") in ["LEASE", "LEASE_ABSTRACT"]:
                self._enrich_lease(doc)
        return documents

    async def _extract_one(self, doc: dict) -> dict:
        doc_type = doc.get("doc_type", "UNKNOWN")

        # Fall back to RENT_ROLL for unknown docs — most uploads are rent rolls
        config = EXTRACTION_PROMPTS.get(doc_type) or EXTRACTION_PROMPTS.get("RENT_ROLL")
        if not config:
            return {"_note": f"No extraction config for {doc_type}"}

        text = doc.get("text", "")
        # Hard cap: send at most 30k chars to extraction to avoid token overflow
        if len(text) > 30000:
            text = text[:15000] + "\n\n[...middle truncated for token limit...]\n\n" + text[-15000:]

        prompt = (
            f"Extract all structured data from this {doc_type} document.\n"
            f"Fields needed: {', '.join(config.get('fields', []))}\n\n"
            f"Document:\n{text}\n\n"
            "Return ONLY valid JSON. For numeric values return bare numbers (no $, commas, or units). "
            "Return null for fields not found. Do NOT include source_text fields in the output."
        )

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": config.get("system", "You are a CRE document analyst. Return only valid JSON.")},
                {"role": "user", "content": prompt},
            ],
        )

        return self._parse_json(response.choices[0].message.content)

    def _enrich_lease(self, doc: dict):
        ext = doc.get("extraction", {})
        expiry = ext.get("lease_expiration_date") or ext.get("expiration_date") or ext.get("lease_end")
        months_remaining = None
        risk_level = "UNKNOWN"

        if expiry:
            try:
                from dateutil import parser
                exp_date = parser.parse(str(expiry))
                today = datetime.now()
                months_remaining = (exp_date.year - today.year) * 12 + (exp_date.month - today.month)
                if months_remaining <= 0:
                    risk_level = "HIGH"
                elif months_remaining <= 6:
                    risk_level = "HIGH"
                elif months_remaining <= 12:
                    risk_level = "HIGH"
                elif months_remaining <= 24:
                    risk_level = "MEDIUM"
                else:
                    risk_level = "LOW"
            except Exception:
                pass

        doc["enriched"] = {"months_remaining": months_remaining, "risk_level": risk_level}

    # =========================================================================
    # STAGE 4: Synthesis
    # =========================================================================

    async def _synthesize(self, deal_name: str, documents: list[dict]) -> dict:
        """Cross-document analysis. Sends only slimmed structured data, never raw text."""
        by_type: dict[str, list] = {}
        for doc in documents:
            dtype = doc.get("doc_type", "UNKNOWN")
            if dtype not in by_type:
                by_type[dtype] = []
            # Strip all raw text before sending to synthesis
            slim_ext = self._slim_extraction(doc.get("extraction", {}))
            by_type[dtype].append({
                "filename": doc.get("filename"),
                "extraction": slim_ext,
                "enriched": doc.get("enriched", {}),
            })

        pa_sf = getattr(self, "_property_appraiser_sf", None)

        pa_block = ""
        if pa_sf:
            pa_block = (
                f"\n*** PROPERTY APPRAISER BASELINE: {pa_sf:,.0f} SF ***\n"
                "This is the authoritative building size from county records.\n"
                "Compare ALL rent roll totals against this number.\n"
                f"If rent roll total SF < {pa_sf:,.0f} SF, tenants are underpaying on square footage.\n"
            )
        else:
            pa_block = "\nNo Property Appraiser SF provided. Compare SF across documents only.\n"

        summary = {
            "deal_name": deal_name,
            "property_appraiser_sf": pa_sf,
            "document_types_present": list(by_type.keys()),
            "document_count": len(documents),
            "extractions": by_type,
        }

        # Hard cap on payload size
        summary_json = json.dumps(summary, indent=2, default=str)
        if len(summary_json) > 60000:
            self.tracer.log("STAGE_4", f"Payload {len(summary_json):,} chars — truncating tenant arrays to 30 rows", "warning")
            for dtype_docs in by_type.values():
                for entry in dtype_docs:
                    ext = entry.get("extraction", {})
                    if isinstance(ext.get("tenants"), list) and len(ext["tenants"]) > 30:
                        ext["tenants"] = ext["tenants"][:30]
            summary["extractions"] = by_type
            summary_json = json.dumps(summary, indent=2, default=str)

        # Single unified prompt — NO separate system prompt to avoid schema conflicts
        prompt = f"""You are a commercial real estate deal analyst. Analyze this CRE deal package and return a comprehensive report.
{pa_block}
DEAL PACKAGE:
{summary_json}

YOU MUST return ONLY valid JSON with EXACTLY these top-level keys. No other keys. No markdown fences.

{{
  "rsf_reconciliation": {{
    "property_appraiser_sf": {pa_sf if pa_sf else 0},
    "rent_roll_total_sf": <sum of all tenant SF from rent roll>,
    "discrepancy_sf": <property_appraiser_sf minus rent_roll_total_sf — positive means tenants underpaying>,
    "discrepancy_pct": <discrepancy_sf / property_appraiser_sf * 100>,
    "alert_triggered": <true if abs(discrepancy_pct) > 2>
  }},
  "rsf_recovery_opportunity": {{
    "recoverable_sf": <discrepancy_sf if positive, else 0>,
    "average_rent_psf": <total annual rent / total tenant SF>,
    "estimated_annual_recovery": <recoverable_sf * average_rent_psf>
  }},
  "tenant_analysis": [
    {{
      "tenant": "<tenant name>",
      "suite": "<suite number>",
      "rsf": <number>,
      "annual_rent": <number>,
      "monthly_rent": <number>,
      "lease_start": "<YYYY-MM-DD or empty string>",
      "lease_end": "<YYYY-MM-DD or empty string>",
      "months_remaining": <integer or null>,
      "risk_level": "<LOW|MEDIUM|HIGH>"
    }}
  ],
  "red_flags": [
    {{
      "severity": "<CRITICAL|HIGH|MODERATE|LOW>",
      "category": "<RSF Discrepancy|Lease Expiration|Data Quality|Financial|Other>",
      "flag": "<short_snake_case_id>",
      "description": "<what the problem is>",
      "impact": "<financial or operational impact>",
      "resolution": "<recommended action>"
    }}
  ],
  "deal_score": {{
    "overall_score": <0-100 integer>,
    "tier": "<GREEN|YELLOW|ORANGE|RED>",
    "data_completeness": <0-100>,
    "rsf_accuracy": <0-100>,
    "lease_health": <0-100>
  }},
  "what_to_get_next": ["<document name>", "<document name>"],
  "financial_summary": {{
    "total_annual_rent": <number>,
    "average_rent_psf": <number>,
    "walt_years": <number or null>
  }}
}}

SCORING: Start at 100. Deduct: 20 if RSF discrepancy >2%, 10 per expiring lease <12mo, 10 if missing rent roll, 5 per unresolved data conflict.
RULES: tenant_analysis MUST list every tenant. All numbers must be bare numbers not strings. Return null not 0 for unknown values."""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        return self._parse_json(response.choices[0].message.content)

    # =========================================================================
    # STAGE 5: Build Final Report
    # =========================================================================

    def _build_report(self, deal_name: str, documents: list[dict], synthesis: dict) -> dict:
        # All keys are lowercase from the new synthesis prompt
        rsf_recon  = synthesis.get("rsf_reconciliation") or {}
        recovery   = synthesis.get("rsf_recovery_opportunity") or {}
        red_flags  = synthesis.get("red_flags") or []
        score_data = synthesis.get("deal_score") or {}
        fin        = synthesis.get("financial_summary") or {}

        # Normalize red_flags to list (AI sometimes returns dict keyed by severity)
        if isinstance(red_flags, dict):
            flat = []
            for sev, flags in red_flags.items():
                if isinstance(flags, list):
                    for f in flags:
                        flat.append(({**f, "severity": sev} if isinstance(f, dict) else {"severity": sev, "description": str(f)}))
            red_flags = flat

        def safe_float(v, default=0.0) -> float:
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(",", "").replace("$", "").strip())
                except Exception:
                    pass
            return default

        score_value = safe_float(
            score_data.get("overall_score")
            or score_data.get("score")
            or score_data.get("overall")
            or 0
        )

        ai_tier = str(score_data.get("tier", "")).upper().strip()
        tier_value = self._normalize_tier(ai_tier) if ai_tier else self._score_to_tier(score_value)

        rsf_recovery_sf = safe_float(
            recovery.get("recoverable_sf") or recovery.get("sf") or recovery.get("discrepancy_sf") or 0
        )
        rsf_recovery_value = safe_float(
            recovery.get("estimated_annual_recovery")
            or recovery.get("annual_value")
            or recovery.get("potential_recovery")
            or 0
        )

        pa_sf = getattr(self, "_property_appraiser_sf", None)

        tenants = self._extract_tenants(synthesis)
        what_next = self._normalize_to_list(
            synthesis.get("what_to_get_next") or []
        )

        return {
            "success": True,
            "deal_name": deal_name,
            "analyzed_at": datetime.utcnow().isoformat(),

            # Top-level fields the frontend reads
            "documents_processed": len(documents),
            "property_appraiser_sf": pa_sf,
            "score": score_value,
            "tier": tier_value,
            "rsf_recovery_sf": rsf_recovery_sf,
            "rsf_recovery_annual_value": rsf_recovery_value,
            "red_flags": red_flags,
            "tenants": tenants,
            "what_to_get_next": what_next,

            # Document list
            "documents": {
                "total": len(documents),
                "by_type": self._count_by_type(documents),
                "files": [
                    {"filename": d.get("filename"), "type": d.get("doc_type"), "confidence": d.get("confidence")}
                    for d in documents
                ],
            },

            # RSF analysis block (nested, for full detail)
            "rsf_analysis": {
                "reconciliation": {**rsf_recon, "property_appraiser_sf": pa_sf},
                "recovery_opportunity": recovery,
                "discrepancy_found": rsf_recovery_sf > 0,
            },

            # Risk block
            "risk": {
                "score": score_value,
                "tier": tier_value,
                "sub_scores": {
                    "data_completeness": safe_float(score_data.get("data_completeness")),
                    "rsf_accuracy": safe_float(score_data.get("rsf_accuracy")),
                    "lease_health": safe_float(score_data.get("lease_health")),
                },
                "red_flags": red_flags,
                "red_flag_count": {
                    "critical": sum(1 for f in red_flags if str(f.get("severity", "")).upper() == "CRITICAL"),
                    "high":     sum(1 for f in red_flags if str(f.get("severity", "")).upper() == "HIGH"),
                    "moderate": sum(1 for f in red_flags if str(f.get("severity", "")).upper() in ("MODERATE", "MEDIUM")),
                    "low":      sum(1 for f in red_flags if str(f.get("severity", "")).upper() == "LOW"),
                },
            },

            # Financial
            "financial": {
                "total_annual_rent": safe_float(fin.get("total_annual_rent")),
                "average_rent_psf": safe_float(fin.get("average_rent_psf")),
                "walt": safe_float(fin.get("walt_years")),
                "noi": safe_float(fin.get("noi")),
                "vacancy": safe_float(fin.get("vacancy")),
            },

            # Lease abstracts (if lease docs present)
            "lease_abstracts": self._extract_lease_abstracts(documents),
        }

    # =========================================================================
    # Helpers
    # =========================================================================

    def _extract_tenants(self, synthesis: dict) -> list:
        """Try every key the AI might use for tenant data."""
        for key in ["tenant_analysis", "TENANT_ANALYSIS", "tenants", "TENANTS", "tenant_roster"]:
            val = synthesis.get(key)
            if val:
                result = self._normalize_to_list(val)
                if result:
                    return result

        # Fallback: old schema keys
        for path in [
            ("rent_verification", "tenant_shares"),
            ("rent_verification", "tenants"),
            ("rent_verification", "tenant_list"),
            ("lease_audit", "tenants"),
            ("lease_audit", "abstracts"),
        ]:
            container = synthesis.get(path[0]) or {}
            if isinstance(container, dict):
                val = container.get(path[1])
                if val:
                    result = self._normalize_to_list(val)
                    if result:
                        return result

        return []

    def _extract_lease_abstracts(self, documents: list[dict]) -> list:
        abstracts = []
        for i, doc in enumerate(documents):
            if doc.get("doc_type") not in ["LEASE", "LEASE_ABSTRACT"]:
                continue
            ext = doc.get("extraction", {})
            abstracts.append({
                "id": f"abstract-{i}",
                "tenant_name": ext.get("tenant_name") or ext.get("tenant", "Unknown"),
                "suite": ext.get("suite_number") or ext.get("suite", ""),
                "rentable_sf": ext.get("rentable_sf") or ext.get("rsf") or 0,
                "lease_commencement": ext.get("lease_commencement_date") or ext.get("lease_start") or "",
                "lease_expiration": ext.get("lease_expiration_date") or ext.get("lease_end"),
                "annual_base_rent": ext.get("base_rent_annual") or ext.get("annual_base_rent") or 0,
                "escalation": ext.get("escalation_type") or ext.get("escalations") or "Unknown",
                "expense_structure": ext.get("expense_structure") or "NNN",
                "missing_fields": [],
            })
        return abstracts

    def _slim_extraction(self, extraction: dict, _depth: int = 0) -> dict:
        """Strip all raw text fields to keep synthesis payload small."""
        if not isinstance(extraction, dict):
            return extraction

        STRIP_KEYS = {"source_text", "raw_text", "raw_text_sample", "_note", "text", "full_text", "page_text"}
        result = {}
        for k, v in extraction.items():
            if k in STRIP_KEYS:
                continue
            if isinstance(v, dict):
                result[k] = self._slim_extraction(v, _depth + 1)
            elif isinstance(v, list):
                result[k] = [
                    self._slim_extraction(item, _depth + 1) if isinstance(item, dict)
                    else (item[:200] + "..." if isinstance(item, str) and len(item) > 200 else item)
                    for item in v
                    if item is not None
                ]
            elif isinstance(v, str) and len(v) > 300:
                result[k] = v[:300] + "..."
            else:
                result[k] = v
        return result

    def _normalize_to_list(self, value) -> list:
        if value is None:
            return []
        if isinstance(value, list):
            return [item for item in value if item is not None]
        if isinstance(value, dict):
            for key in ("tenants", "items", "list"):
                if key in value:
                    return self._normalize_to_list(value[key])
            return [value] if value else []
        return [value]

    def _count_by_type(self, documents: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for doc in documents:
            t = doc.get("doc_type", "UNKNOWN")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def _score_to_tier(self, score: float) -> str:
        if score >= 85:
            return "GREEN"
        elif score >= 70:
            return "YELLOW"
        elif score >= 50:
            return "ORANGE"
        return "RED"

    def _normalize_tier(self, tier_str: str) -> str:
        mapping = {
            "GREEN": "GREEN", "PASS": "GREEN", "LOW RISK": "GREEN",
            "YELLOW": "YELLOW", "CAUTION": "YELLOW", "UNDER REVIEW": "YELLOW", "MODERATE RISK": "YELLOW",
            "ORANGE": "ORANGE", "HIGH RISK": "ORANGE", "ELEVATED": "ORANGE",
            "RED": "RED", "CRITICAL": "RED", "FAIL": "RED", "VERY HIGH RISK": "RED",
        }
        t = tier_str.upper().strip()
        return mapping.get(t, self._score_to_tier(0))

    def _parse_json(self, text: str) -> dict:
        """Robustly extract JSON from AI response, handling markdown fences and partial JSON."""
        if not text:
            return {}
        # Strip markdown fences
        text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON block
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            return {}

    def _to_deal_analysis(self, report: dict) -> DealAnalysis:
        return DealAnalysis(
            deal_name=report.get("deal_name", ""),
            overall_score=report.get("score", 0),
            tier=report.get("tier", "UNKNOWN"),
            sub_scores=report.get("risk", {}).get("sub_scores", {}),
            red_flags=[
                RedFlag(
                    severity=Severity(f.get("severity", "LOW")),
                    category=f.get("category", "GENERAL"),
                    flag=f.get("flag", ""),
                    impact=f.get("impact", ""),
                    resolution=f.get("resolution", ""),
                )
                for f in report.get("red_flags", [])
                if f and isinstance(f, dict)
            ],
            tenants=report.get("tenants", []),
            rsf_reconciliation=report.get("rsf_analysis", {}).get("reconciliation", {}),
            what_to_get_next=report.get("what_to_get_next", []),
        )
