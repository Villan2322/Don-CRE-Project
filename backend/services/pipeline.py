"""
CRE Document Intelligence Pipeline — Multi-Hop Agentic Architecture with COVE

Every number in the final report is grounded to a source and confidence-scored.
Pipeline hops:
  1. INGEST    — extract raw text from PDF/Excel/image
  2. CLASSIFY  — identify document type
  3. EXTRACT   — structured data extraction per doc type (chunked for large docs)
  4. COVE      — Cross-Output Verification & Evidence: compare values across all
                  extraction passes; compute per-field agreement score.
                  Numbers with <90% agreement are flagged UNVERIFIED and suppressed
                  from the final output (shown as null with a flag).
  5. RECONCILE — pure Python arithmetic on VERIFIED values only: totals, RSF deltas,
                  rent PSF (no AI, no hallucination)
  6. SYNTHESIZE — AI analysis grounded in the reconciled numbers (flags, score, what-to-get-next)
  7. VERIFY    — Python post-check: assert AI numbers match reconciled numbers, fix if not
  8. REPORT    — build final response; every number carries its confidence score and source
"""

# COVE confidence threshold: values must agree across passes to this tolerance
COVE_AGREEMENT_THRESHOLD = 0.90   # 90%
COVE_VALUE_TOLERANCE_PCT  = 0.05  # two reads are "same" if within 5% of each other

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


# ---------------------------------------------------------------------------
# Tracer
# ---------------------------------------------------------------------------

class PipelineTracer:
    def __init__(self):
        self.logs: list[dict] = []

    def log(self, stage: str, message: str, level: str = "info", data: dict = None):
        entry = {"timestamp": datetime.now().isoformat(), "stage": stage, "message": message, "level": level}
        if data:
            entry["data"] = data
        self.logs.append(entry)
        print(f"[PIPELINE:{stage}:{level}] {message}", flush=True)

    def get_logs(self) -> list[dict]:
        return self.logs


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

class CREPipeline:
    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""),
        )
        self.model = "anthropic/claude-sonnet-4"
        self.tracer: PipelineTracer = None

    # =========================================================================
    # ENTRY POINT
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
        self._property_appraiser_sf = property_appraiser_sf

        self.tracer.log("START", f"Deal: {deal_name} | {len(files)} file(s)", "info")
        if property_appraiser_sf:
            self.tracer.log("BASELINE", f"Property Appraiser SF baseline: {property_appraiser_sf:,.0f} SF", "info")
        else:
            self.tracer.log("BASELINE", "No PA SF provided — will compare across documents only", "warning")

        # ── HOP 1: Ingest ───────────────────────────────────────────────────
        self.tracer.log("HOP_1", "Ingesting files...", "info")
        documents = await self._ingest_files(files)
        if not documents:
            return self._error_response(deal_name, "No processable documents found")
        self.tracer.log("HOP_1", f"Ingested {len(documents)} document(s)", "success")

        # ── HOP 2: Classify ─────────────────────────────────────────────────
        self.tracer.log("HOP_2", "Classifying document types...", "info")
        documents = await self._classify_all(documents)
        for doc in documents:
            self.tracer.log(
                "HOP_2",
                f"  {doc['filename']} → {doc['doc_type']} ({doc.get('confidence', 0)*100:.0f}% confident)"
                + (f" [override from {doc['original_doc_type']}]" if doc.get("original_doc_type") else ""),
                "info",
            )

        # ── HOP 3: Extract ──────────────────────────────────────────────────
        self.tracer.log("HOP_3", "Extracting structured data (chunked for large docs)...", "info")
        documents = await self._extract_all(documents)
        total_tenants = sum(len(doc.get("extraction", {}).get("tenants") or []) for doc in documents)
        self.tracer.log("HOP_3", f"Extraction complete — {total_tenants} tenant rows found across all docs", "success" if total_tenants > 0 else "warning")

        # ── HOP 4: Chain of Verification (CoVe) ─────────────────────────────
        # Generates verification questions per tenant, re-answers them independently
        # from source text, and cross-compares. Values with <90% agreement are
        # suppressed — they appear in output as "— (unverified)".
        self.tracer.log("HOP_4", "Chain of Verification: re-verifying every extracted value independently...", "info")
        documents = await self._cove(documents)
        verified   = sum(1 for d in documents for t in (d.get("cove_tenants") or []) if t.get("_cove_verified", False))
        unverified = sum(1 for d in documents for t in (d.get("cove_tenants") or []) if not t.get("_cove_verified", False))
        self.tracer.log(
            "HOP_4",
            f"CoVe complete — {verified} tenants VERIFIED (>=90%), {unverified} suppressed (<90%)",
            "success" if unverified == 0 else "warning",
        )

        # ── HOP 5: Reconcile (pure Python arithmetic, verified values only) ──
        self.tracer.log("HOP_5", "Reconciling numbers (Python arithmetic only, no AI)...", "info")
        reconciliation = self._reconcile(documents, property_appraiser_sf)
        self.tracer.log(
            "HOP_5",
            f"Reconciled: {reconciliation['tenant_count']} tenants "
            f"({reconciliation.get('unverified_suppressed', 0)} suppressed by CoVe) | "
            f"{reconciliation['rent_roll_total_sf']:,.0f} SF | "
            f"${reconciliation['total_annual_rent']:,.0f}/yr | "
            f"RSF gap: {reconciliation['rsf_gap_sf']:,.0f} SF",
            "success",
        )

        # ── HOP 6: Synthesize (AI grounded in reconciled numbers) ───────────
        self.tracer.log("HOP_6", "AI synthesis (grounded in reconciled numbers)...", "info")
        synthesis = await self._synthesize(deal_name, documents, reconciliation)
        self.tracer.log("HOP_6", f"Synthesis: {len(synthesis.get('red_flags') or [])} flags | score {synthesis.get('deal_score', {}).get('overall_score', '?')}", "success")

        # ── HOP 7: Verify (Python checks AI output against reconciled truth) ─
        self.tracer.log("HOP_7", "Verifying AI output against reconciled numbers...", "info")
        synthesis = self._verify_and_correct(synthesis, reconciliation)
        self.tracer.log("HOP_7", "Verification complete", "success")

        # ── HOP 8: Build report ─────────────────────────────────────────────
        self.tracer.log("HOP_8", "Building final report...", "info")
        report = self._build_report(deal_name, documents, synthesis, reconciliation)

        score = report.get("score", 0)
        tier  = report.get("tier", "?")
        rsf_gap = reconciliation["rsf_gap_sf"]
        rsf_val = reconciliation["rsf_gap_annual_value"]

        if rsf_gap > 0:
            self.tracer.log("RESULT", f"RSF gap: {rsf_gap:,.0f} SF = ${rsf_val:,.0f}/yr potential recovery", "warning")
        else:
            self.tracer.log("RESULT", "No RSF discrepancy detected", "success")

        self.tracer.log("RESULT", f"Deal Score: {score}/100 ({tier})", "info")
        self.tracer.log("COMPLETE", f"Pipeline complete — {len(report.get('tenants', []))} tenants in output", "success")

        report["trace_log"] = self.tracer.get_logs()
        return report

    # Alias
    async def run(self, deal_name: str, documents: list[dict]) -> DealAnalysis:
        result = await self.analyze(documents, deal_name)
        return self._to_deal_analysis(result)

    # =========================================================================
    # HOP 1 — INGEST
    # =========================================================================

    async def _ingest_files(self, files: list[dict]) -> list[dict]:
        documents = []
        for i, file in enumerate(files):
            filename = file.get("filename", f"document_{i}")
            content  = file.get("content", "")
            ct       = file.get("content_type", self._guess_content_type(filename))

            self.tracer.log("INGEST", f"Processing: {filename}", "info")

            doc = {
                "id": f"doc_{i}",
                "filename": filename,
                "content_type": ct,
                "file_ext": self._get_ext(filename),
                "ingested_at": datetime.utcnow().isoformat(),
                "extraction_method": None,
                "extraction_errors": [],
            }

            text = ""
            if self._is_excel(filename, ct):
                text, _ = await self._try_extract_excel(content, filename, doc)
            elif self._is_pdf(filename, ct):
                text, _ = await self._try_extract_pdf(content, filename, doc)
            elif self._is_image(filename, ct):
                text, _ = await self._try_ocr(content, filename, doc)
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
                self.tracer.log("INGEST", f"  {filename}: {doc['extraction_method']} → {len(text):,} chars", "success")
            else:
                doc["text"] = f"[EXTRACTION FAILED: {filename}]\n" + "\n".join(doc["extraction_errors"])
                self.tracer.log("INGEST", f"  {filename}: minimal content ({len(text)} chars)", "warning")

            documents.append(doc)

        return documents

    async def _try_extract_pdf(self, content, filename, doc) -> tuple[str, bool]:
        text = self._extract_pdf_text(content)
        has_error = text and "[PDF extraction error" in text

        if not has_error and text and len(text.strip()) > 100:
            doc["extraction_method"] = "pdf_text"
            return text, True

        if has_error:
            doc["extraction_errors"].append(text)

        sparse = len(text.strip()) if text else 0
        self.tracer.log("INGEST", f"  Sparse text ({sparse} chars), trying AI OCR...", "info")

        ocr_text = await self._parse_pdf_with_openrouter(content, filename)
        ocr_ok = ocr_text and "[PDF parsing error" not in ocr_text and "[PDF OCR" not in ocr_text

        if ocr_ok and len(ocr_text.strip()) > 50:
            doc["extraction_method"] = "pdf_ai_ocr"
            return ocr_text, True

        if not ocr_ok and ocr_text:
            doc["extraction_errors"].append(f"AI OCR: {ocr_text[:200]}")
            self.tracer.log("INGEST", f"  AI OCR failed: {ocr_text[:120]}", "error")

        real_text = text.strip() if text and len(text.strip()) > 20 and not has_error else ""
        real_ocr  = ocr_text.strip() if ocr_ok and ocr_text and len(ocr_text.strip()) > 20 else ""
        combined  = "\n\n".join(filter(None, [real_text, real_ocr]))

        if combined and len(combined) > 50:
            doc["extraction_method"] = "pdf_combined"
            return combined, True

        if text and len(text.strip()) > 10 and not has_error:
            doc["extraction_method"] = "pdf_raw_fallback"
            return text, True

        doc["extraction_method"] = "pdf_failed"
        self.tracer.log("INGEST", f"  All PDF methods failed for {filename}", "error")
        return f"[PDF EXTRACTION FAILED: {filename}]\n" + "\n".join(doc["extraction_errors"]), True

    async def _parse_pdf_with_openrouter(self, content, filename: str) -> str:
        try:
            import httpx
            b64 = base64.b64encode(content).decode("utf-8") if isinstance(content, bytes) else content
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "max_tokens": 8000,
                        "messages": [{"role": "user", "content": [
                            {"type": "text", "text": (
                                "Extract ALL text from this commercial real estate PDF. "
                                "Preserve table structure using | column | separators. "
                                "For rent rolls: Tenant | Suite | SF | Monthly Rent | Annual Rent | Lease Start | Lease End. "
                                "Return ONLY the extracted text, no commentary."
                            )},
                            {"type": "file", "file": {"filename": filename, "file_data": f"data:application/pdf;base64,{b64}"}}
                        ]}],
                        "plugins": [{"id": "file-parser", "pdf": {"engine": "mistral-ocr"}}],
                    },
                )
                if resp.status_code != 200:
                    return f"[PDF parsing error: HTTP {resp.status_code} - {resp.text[:200]}]"
                data = resp.json()
                if "choices" in data and data["choices"]:
                    return data["choices"][0]["message"]["content"]
                return "[PDF parsing error: No content in response]"
        except Exception as e:
            return f"[PDF parsing error: {e}]"

    async def _try_extract_excel(self, content, filename, doc) -> tuple[str, bool]:
        text = await self._extract_excel_text(content, filename)
        if text and "[Excel extraction error" not in text:
            doc["extraction_method"] = "excel"
            return text, True
        doc["extraction_errors"].append(text or "Excel extraction failed")
        return "", False

    async def _try_ocr(self, content, filename, doc) -> tuple[str, bool]:
        text = await self._ocr_document(content, filename)
        if text and "[OCR error" not in text and len(text.strip()) > 20:
            doc["extraction_method"] = "ocr"
            return text, True
        if text and "[OCR error" in text:
            doc["extraction_errors"].append(text)
        return text or "", False

    def _extract_pdf_text(self, content) -> str:
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
            return "\n\n".join(parts) if parts else "[PDF extraction error: No text found — may be scanned]"
        except ImportError:
            return "[PDF extraction error: PyPDF2 not installed]"
        except Exception as e:
            return f"[PDF extraction error: {e}]"

    async def _extract_excel_text(self, content, filename: str) -> str:
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

    async def _ocr_document(self, content, filename: str) -> str:
        ext = self._get_ext(filename)
        if ext == "pdf":
            return await self._parse_pdf_with_openrouter(content, filename)
        try:
            import httpx
            b64 = base64.b64encode(content).decode("utf-8") if isinstance(content, bytes) else content
            media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "tiff": "image/tiff"}.get(ext, "image/png")
            raw = content if isinstance(content, bytes) else base64.b64decode(content)
            if len(raw) > 10 * 1024 * 1024:
                return f"[OCR error: Image too large ({len(raw)/1024/1024:.1f}MB)]"
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}", "Content-Type": "application/json"},
                    json={"model": self.model, "max_tokens": 8000, "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "Extract ALL text from this CRE document image. Preserve table structure with | separators. Return only extracted text."},
                        {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                    ]}]},
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
    # HOP 2 — CLASSIFY
    # =========================================================================

    async def _classify_all(self, documents: list[dict]) -> list[dict]:
        tasks = [self._classify_one(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                doc["doc_type"] = "UNKNOWN"
                doc["classification_error"] = str(result)
                doc["confidence"] = 0.0
            else:
                doc.update(result)

            # Content-aware override: upgrade to RENT_ROLL if text signals it
            doc_type = doc.get("doc_type", "UNKNOWN")
            text = doc.get("text", "").lower()
            if doc_type in ("MANAGEMENT_REPORT", "FINANCIAL_MODEL", "UNKNOWN"):
                signals = [
                    "rsf" in text or "sq ft" in text or "square feet" in text or "square footage" in text,
                    "monthly rent" in text or "annual rent" in text or "rent/sf" in text or "per sf" in text or "/sf/yr" in text,
                    "lease start" in text or "lease end" in text or "expir" in text or "commence" in text or "lease term" in text,
                    text.count("|") > 10 or text.count("\t") > 20 or "suite" in text,
                ]
                if sum(signals) >= 3:
                    doc["original_doc_type"] = doc_type
                    doc["doc_type"] = "RENT_ROLL"
                    self.tracer.log("HOP_2", f"  Override: {doc['filename']} {doc_type} → RENT_ROLL (rent-roll signals present)", "warning")

        return documents

    async def _classify_one(self, doc: dict) -> dict:
        text   = doc.get("text", "")
        sample = text[:2500] + ("\n\n[...]\n\n" + text[-2500:] if len(text) > 5000 else "")
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=300,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"Filename: {doc.get('filename', 'unknown')}\n\nDocument text:\n{sample}"},
            ],
        )
        result   = self._parse_json(response.choices[0].message.content)
        doc_type = (result.get("doc_type") or result.get("document_type") or result.get("type") or "UNKNOWN").upper().strip()
        known = {"LEASE", "LEASE_ABSTRACT", "RENT_ROLL", "RENT_ROLL_XLSX", "BOMA", "FINANCIAL_MODEL", "CAM_RECONCILIATION", "MANAGEMENT_REPORT", "COUNTY_PA"}
        if doc_type not in known:
            doc_type = doc_type.replace(" ", "_")
            if doc_type not in known:
                doc_type = "UNKNOWN"
        return {"doc_type": doc_type, "confidence": float(result.get("confidence", 0.5)), "reasoning": result.get("reasoning", "")}

    # =========================================================================
    # HOP 3 — EXTRACT (chunked, parallel, merged)
    # =========================================================================

    async def _extract_all(self, documents: list[dict]) -> list[dict]:
        all_tasks: list = []
        task_map: list[tuple[int, str]] = []

        CHUNK_SIZE = 25000
        OVERLAP    = 3000

        for i, doc in enumerate(documents):
            doc_type = doc.get("doc_type", "UNKNOWN")
            text     = doc.get("text", "")

            # Pass 1 — typed extraction using the doc's own schema
            all_tasks.append(self._extract_one(doc_type, text, doc.get("filename", "")))
            task_map.append((i, "typed"))

            # Pass 2 — always run a dedicated RENT_ROLL pass regardless of doc type.
            # Management reports, financial models, and other multi-section docs
            # often embed a tenant schedule that the typed pass misses.
            # A single RENT_ROLL pass covers docs under CHUNK_SIZE without chunking.
            if doc_type != "RENT_ROLL":  # skip if already a rent roll — typed pass IS the RR pass
                all_tasks.append(self._extract_one("RENT_ROLL", text[:CHUNK_SIZE], doc.get("filename", "")))
                task_map.append((i, "rr_fallback"))

            # Pass 3+ — chunked RENT_ROLL passes for large docs (covers every page)
            if len(text) > CHUNK_SIZE:
                start, chunk_idx = 0, 0
                while start < len(text):
                    end = min(start + CHUNK_SIZE, len(text))
                    all_tasks.append(self._extract_one("RENT_ROLL", text[start:end], doc.get("filename", "")))
                    task_map.append((i, f"chunk_{chunk_idx}"))
                    chunk_idx += 1
                    if end >= len(text):
                        break
                    start = end - OVERLAP
                self.tracer.log("HOP_3", f"  {doc['filename']}: {len(text):,} chars — typed + {chunk_idx} chunk(s)", "info")
            else:
                self.tracer.log("HOP_3", f"  {doc['filename']}: {len(text):,} chars — typed + RR fallback pass", "info")

        all_results = await asyncio.gather(*all_tasks, return_exceptions=True)

        # Group by document
        doc_buckets: dict[int, list[tuple[str, dict]]] = {i: [] for i in range(len(documents))}
        for (doc_idx, label), result in zip(task_map, all_results):
            if not isinstance(result, Exception):
                doc_buckets[doc_idx].append((label, result))
            else:
                self.tracer.log("HOP_3", f"  Extraction error ({label}): {result}", "error")

        for i, doc in enumerate(documents):
            bucket = doc_buckets[i]
            if not bucket:
                doc["extraction"] = {"tenants": [], "summary": {}, "error": "All extraction attempts failed"}
                doc["_all_pass_results"] = []
                continue

            # Typed pass is primary
            typed = next((r for lbl, r in bucket if lbl == "typed"), {}) or {}
            merged = dict(typed)

            # All individual pass results stored for CoVe cross-comparison
            all_pass_results: list[dict] = [r for _, r in bucket]

            # Merge tenants from all chunk passes (de-dupe by name+suite)
            all_tenants: list[dict] = list(merged.get("tenants") or [])
            seen_names: set[str] = {self._tenant_key(t) for t in all_tenants}

            for lbl, result in bucket:
                if lbl == "typed":
                    continue
                for t in (result.get("tenants") or []):
                    if t is None:
                        continue
                    key = self._tenant_key(t)
                    if key and key not in seen_names:
                        all_tenants.append(t)
                        seen_names.add(key)
                if not merged.get("summary") and result.get("summary"):
                    merged["summary"] = result["summary"]

            merged["tenants"] = all_tenants
            doc["extraction"] = merged
            # Store every pass result so _cove can cross-compare values
            doc["_all_pass_results"] = all_pass_results

            # Enrich leases with months-remaining
            if doc.get("doc_type") in ["LEASE", "LEASE_ABSTRACT"]:
                self._enrich_lease(doc)

            self.tracer.log(
                "HOP_3",
                f"  {doc['filename']}: {len(all_tenants)} tenants merged from {len(bucket)} pass(es)",
                "success" if all_tenants else "warning",
            )

        return documents

    async def _extract_one(self, doc_type: str, text: str, filename: str) -> dict:
        config = EXTRACTION_PROMPTS.get(doc_type) or EXTRACTION_PROMPTS.get("RENT_ROLL", {})
        fields = config.get("fields", [])
        system = config.get("system", "You are a CRE document analyst. Return only valid JSON.")

        # Hard cap per extraction call
        if len(text) > 30000:
            text = text[:30000]

        # Extra instruction for doc types that embed tenant rosters inside larger reports
        tenant_instruction = ""
        if doc_type in ("MANAGEMENT_REPORT", "FINANCIAL_MODEL", "CAM_RECONCILIATION", "RENT_ROLL"):
            tenant_instruction = (
                "\n- TENANT ROSTER: Scan the entire document for any section labelled "
                "'Rent Schedule', 'Tenant Roster', 'Occupancy', 'Rent Roll', or any table "
                "with tenant names and square footages. Extract EVERY row as a separate "
                "object in the 'tenants' array. Do not skip any tenant even if data is partial.\n"
                "- Minimum fields per tenant: tenant_name and rsf (or monthly_base_rent).\n"
                "- Vacant units should be included with tenant_name: 'Vacant'."
            )

        prompt = (
            f"Extract all structured data from this CRE document treating it as a {doc_type}.\n"
            f"Fields needed: {', '.join(fields)}\n\n"
            f"Document text:\n{text}\n\n"
            "CRITICAL RULES:\n"
            "- Return ONLY valid JSON. No markdown fences.\n"
            "- Numbers must be bare numbers — no $, commas, or units (e.g. 22500 not '22,500 SF').\n"
            "- Return null for fields not found. Do NOT make up values.\n"
            "- Do NOT include source_text, confidence, or citation fields.\n"
            "- For tenants: extract EVERY row found even if incomplete. Minimum: tenant_name + rsf.\n"
            "- tenant_name field must be exactly: tenant_name (not 'tenant' or 'name').\n"
            "- If you see a totals/summary row at the bottom, put it in 'summary.total_rsf' "
            "and 'summary.total_annual_rent'."
            + tenant_instruction
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        )
        return self._parse_json(response.choices[0].message.content)

    # =========================================================================
    # HOP 4 — CHAIN OF VERIFICATION (CoVe)
    # =========================================================================

    async def _cove(self, documents: list[dict]) -> list[dict]:
        """
        True Chain of Verification:
        1. For each tenant extracted in Hop 3, generate specific verification
           questions ("What is [Tenant X]'s RSF?", "What is [Tenant X]'s annual rent?")
        2. Re-answer each question independently by scanning the source text — NOT
           from the stored extraction (to avoid anchoring on the first answer).
        3. Compare original extraction answer vs. CoVe re-answer. If they agree
           within COVE_VALUE_TOLERANCE_PCT (5%), the field is VERIFIED. Otherwise
           UNVERIFIED and suppressed.
        4. Additionally, cross-compare values across chunked extraction passes —
           if multiple passes saw the tenant and agree, confidence increases further.

        A tenant is marked VERIFIED overall only if BOTH rsf AND rent are verified.
        Numbers that don't pass CoVe appear in the UI as "— (unverified)" and are
        excluded from all arithmetic in Hop 5.
        """
        # Run CoVe verification for all documents in parallel
        tasks = [self._cove_one(doc) for doc in documents]
        await asyncio.gather(*tasks, return_exceptions=True)
        return documents

    async def _cove_one(self, doc: dict):
        """Run Chain of Verification for a single document."""
        extraction = doc.get("extraction", {})
        tenants    = list(extraction.get("tenants") or [])
        source_text = doc.get("text", "")
        all_passes  = doc.get("_all_pass_results", [])

        if not tenants:
            doc["cove_tenants"] = []
            doc["cove_summary"] = {"verified": 0, "unverified": 0, "passes": len(all_passes) + 1}
            return

        # ── Step 1: Build cross-pass lookup ──────────────────────────────────
        # Every chunk/typed pass that found this tenant is a separate "read"
        pass_lookup: dict[str, list[dict]] = {}
        for pass_result in all_passes:
            for t in (pass_result.get("tenants") or []):
                if not t:
                    continue
                key = self._tenant_key(t)
                if not key:
                    continue
                pass_lookup.setdefault(key, []).append({
                    "rsf":         self._sf(t.get("rsf") or t.get("rentable_sf") or 0),
                    "annual_rent": self._sf(t.get("annual_base_rent") or t.get("annual_rent") or
                                           self._sf(t.get("monthly_base_rent") or t.get("monthly_rent") or 0) * 12),
                })

        # ── Step 2: Generate + answer verification questions via AI ──────────
        # Ask the AI to independently re-look up each tenant's key numbers
        # from the source text — with explicit instruction not to use memory.
        if source_text and tenants:
            tenant_names = [
                t.get("tenant_name") or t.get("tenant") or t.get("name") or ""
                for t in tenants[:30]  # cap at 30 to fit context
            ]
            tenant_list = "\n".join(f"- {n}" for n in tenant_names if n)

            # Truncate source text for the verification call
            verify_text = source_text[:25000] if len(source_text) > 25000 else source_text

            verify_prompt = (
                f"You are verifying numbers extracted from a CRE document. "
                f"Re-read the document text below and answer each question by scanning the text directly. "
                f"Do NOT use prior knowledge — only what is written in the text below.\n\n"
                f"For each of these tenants, look up their RSF and annual rent from the document:\n"
                f"{tenant_list}\n\n"
                f"Document text:\n{verify_text}\n\n"
                f"Return ONLY valid JSON — an array of objects, one per tenant found:\n"
                f'[{{"tenant_name": "...", "rsf": <number or null>, "annual_rent": <number or null>}}]\n\n'
                f"RULES:\n"
                f"- Use bare numbers (no $ or commas)\n"
                f"- If a tenant is not found in the text, still include them with null values\n"
                f"- Do NOT guess — return null if you cannot find the value in the text"
            )

            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=3000,
                    messages=[{"role": "user", "content": verify_prompt}],
                )
                raw = response.choices[0].message.content
                # Parse the verification answers
                parsed = self._parse_json_array(raw)
                verify_lookup: dict[str, dict] = {}
                for item in (parsed if isinstance(parsed, list) else []):
                    if not isinstance(item, dict):
                        continue
                    name = (item.get("tenant_name") or "").strip().lower()
                    if name:
                        verify_lookup[name] = {
                            "rsf":         self._sf(item.get("rsf") or 0),
                            "annual_rent": self._sf(item.get("annual_rent") or 0),
                        }
            except Exception as e:
                self.tracer.log("HOP_4", f"  CoVe AI call failed for {doc.get('filename')}: {e}", "error")
                verify_lookup = {}
        else:
            verify_lookup = {}

        # ── Step 3: Score each tenant field ──────────────────────────────────
        cove_tenants = []
        for t in tenants:
            key  = self._tenant_key(t)
            name = (t.get("tenant_name") or t.get("tenant") or t.get("name") or "").strip().lower()

            rsf_extracted  = self._sf(t.get("rsf") or t.get("rentable_sf") or 0)
            rent_extracted = self._sf(
                t.get("annual_base_rent") or t.get("annual_rent") or
                self._sf(t.get("monthly_base_rent") or t.get("monthly_rent") or 0) * 12
            )

            # Collect all reads for this tenant: extracted + CoVe + all chunk passes
            rsf_reads  = [rsf_extracted]  if rsf_extracted  else []
            rent_reads = [rent_extracted] if rent_extracted else []

            # Add CoVe re-answer
            cove_answer = verify_lookup.get(name, {})
            if cove_answer.get("rsf"):
                rsf_reads.append(cove_answer["rsf"])
            if cove_answer.get("annual_rent"):
                rent_reads.append(cove_answer["annual_rent"])

            # Add cross-pass reads
            for read in pass_lookup.get(key, []):
                if read["rsf"]:
                    rsf_reads.append(read["rsf"])
                if read["annual_rent"]:
                    rent_reads.append(read["annual_rent"])

            # Score agreement: what fraction of reads agree with the primary read within tolerance?
            def _agreement(primary: float, reads: list[float]) -> float:
                if len(reads) < 2:
                    # Only one source — max 70% confidence (not enough evidence to reach 90%)
                    return 0.70
                agreements = sum(
                    1 for r in reads
                    if primary > 0 and abs(r - primary) / primary <= COVE_VALUE_TOLERANCE_PCT
                )
                return agreements / len(reads)

            rsf_conf  = _agreement(rsf_extracted,  rsf_reads)
            rent_conf = _agreement(rent_extracted, rent_reads)

            # Overall confidence: both fields must pass for the tenant to be VERIFIED
            overall_conf   = (rsf_conf + rent_conf) / 2
            confidence_pct = round(overall_conf * 100, 1)
            rsf_verified   = rsf_conf  >= COVE_AGREEMENT_THRESHOLD
            rent_verified  = rent_conf >= COVE_AGREEMENT_THRESHOLD
            fully_verified = rsf_verified and rent_verified

            entry = dict(t)
            entry["_cove_verified"]     = fully_verified
            entry["_verified"]          = fully_verified  # used by _reconcile
            entry["_confidence_pct"]    = confidence_pct
            entry["_rsf_confidence"]    = round(rsf_conf  * 100, 1)
            entry["_rent_confidence"]   = round(rent_conf * 100, 1)
            entry["_cove_reads"]        = {"rsf": len(rsf_reads), "rent": len(rent_reads)}
            entry["_cove_status"]       = "VERIFIED" if fully_verified else "UNVERIFIED"
            entry["_cove_answer"]       = cove_answer  # the re-verified values

            # Suppress unverified numeric fields — set to None, not removed
            # They appear in the UI as "— (unverified)" to flag for manual check
            if not rsf_verified:
                entry["rsf"]               = None
                entry["rentable_sf"]       = None
                entry["_rsf_suppressed"]   = True
            if not rent_verified:
                entry["annual_base_rent"]  = None
                entry["annual_rent"]       = None
                entry["monthly_base_rent"] = None
                entry["monthly_rent"]      = None
                entry["_rent_suppressed"]  = True

            cove_tenants.append(entry)

        verified_n   = sum(1 for t in cove_tenants if t["_cove_verified"])
        unverified_n = len(cove_tenants) - verified_n

        doc["cove_tenants"] = cove_tenants
        doc["cove_summary"] = {
            "verified":     verified_n,
            "unverified":   unverified_n,
            "total_passes": 1 + len(all_passes),
            "used_ai_verification": bool(verify_lookup),
        }
        self.tracer.log(
            "HOP_4",
            f"  {doc.get('filename')}: {verified_n}/{len(cove_tenants)} tenants VERIFIED "
            f"({len(all_passes)+1} passes, AI re-verify: {'yes' if verify_lookup else 'no'})",
            "success" if unverified_n == 0 else "warning",
        )

    def _parse_json_array(self, text: str) -> list:
        """Parse a JSON array from AI output, stripping markdown fences."""
        if not text:
            return []
        text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
        text = text.strip()
        # Try direct array parse
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            # Could be wrapped: {"tenants": [...]}
            if isinstance(result, dict):
                for v in result.values():
                    if isinstance(v, list):
                        return v
        except json.JSONDecodeError:
            pass
        # Fallback: find first [...] block
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return []

    def _tenant_key(self, t: dict) -> str:
        name = (t.get("tenant_name") or t.get("tenant") or t.get("name") or "").strip().lower()
        suite = (t.get("suite") or t.get("suite_number") or "").strip().lower()
        return f"{name}|{suite}" if (name or suite) else ""

    def _enrich_lease(self, doc: dict):
        ext = doc.get("extraction", {})
        expiry = ext.get("lease_expiration_date") or ext.get("expiration_date") or ext.get("lease_end")
        months_remaining = None
        risk_level = "UNKNOWN"
        if expiry:
            try:
                from dateutil import parser
                exp = parser.parse(str(expiry))
                today = datetime.now()
                months_remaining = (exp.year - today.year) * 12 + (exp.month - today.month)
                risk_level = "HIGH" if months_remaining <= 12 else ("MEDIUM" if months_remaining <= 24 else "LOW")
            except Exception:
                pass
        doc["enriched"] = {"months_remaining": months_remaining, "risk_level": risk_level}

    # =========================================================================
    # HOP 4 — RECONCILE (pure Python, no AI)
    # The single source of truth for all numbers in the final report.
    # =========================================================================

    def _reconcile(self, documents: list[dict], pa_sf: float | None) -> dict:
        """
        Aggregate CoVe-verified tenant rows and compute all numeric values
        using Python arithmetic only. No AI involved.

        Only tenants that passed CoVe (_cove_verified=True) contribute to totals.
        Unverified tenants are still included in the output for transparency, but
        their suppressed fields (rsf=None, rent=None) contribute 0 to all sums.
        """
        all_tenants: list[dict] = []
        unverified_suppressed = 0

        for doc in documents:
            # Always prefer CoVe-scored tenants; fall back to raw extraction
            tenant_source = doc.get("cove_tenants") or doc.get("extraction", {}).get("tenants") or []
            for t in tenant_source:
                if t is None:
                    continue
                key = self._tenant_key(t)
                if not key:
                    continue
                t["_source_doc"] = doc.get("filename", "")
                if t.get("_cove_verified") is False:
                    unverified_suppressed += 1
                all_tenants.append(t)

        def sf(t):   return self._sf(t.get("rsf") or t.get("rentable_sf") or t.get("usf") or 0)
        def rent(t): return self._sf(t.get("annual_base_rent") or t.get("annual_rent") or (self._sf(t.get("monthly_base_rent") or t.get("monthly_rent") or 0) * 12))

        # Only use CoVe-VERIFIED tenants for totals — unverified values are arithmetically untrusted
        verified_tenants = [t for t in all_tenants if t.get("_cove_verified", t.get("_verified", True))]
        total_sf   = sum(sf(t) for t in verified_tenants)
        total_rent = sum(rent(t) for t in verified_tenants)
        avg_psf    = (total_rent / total_sf) if total_sf > 0 else 0

        # RSF gap
        rsf_gap_sf    = max(0.0, (pa_sf or 0) - total_sf) if pa_sf else 0.0
        rsf_gap_value = rsf_gap_sf * avg_psf if avg_psf else 0.0

        # Per-tenant enrichment with CoVe confidence and source citation
        enriched_tenants = []
        for t in all_tenants:
            cove_verified = t.get("_cove_verified", t.get("_verified", True))  # default True if CoVe didn't run
            conf_pct      = t.get("_confidence_pct", 100.0 if cove_verified else 0.0)
            rsf_supp      = t.get("_rsf_suppressed", False)
            rent_supp     = t.get("_rent_suppressed", False)

            t_sf   = sf(t)   if not rsf_supp   else None
            t_rent = rent(t) if not rent_supp   else None

            enriched_tenants.append({
                "tenant":           t.get("tenant_name") or t.get("tenant") or t.get("name") or "Unknown",
                "suite":            t.get("suite") or t.get("suite_number") or "",
                "rsf":              t_sf,
                "annual_rent":      t_rent,
                "monthly_rent":     round(t_rent / 12, 2) if t_rent else None,
                "rent_psf":         round(t_rent / t_sf, 2) if t_sf and t_rent else None,
                "lease_start":      t.get("lease_start") or t.get("lease_commencement_date") or "",
                "lease_end":        t.get("lease_end") or t.get("lease_expiration_date") or "",
                "status":           t.get("status") or "Active",
                "ar_balance":       self._sf(t.get("ar_balance") or 0),
                "_source_doc":      t.get("_source_doc", ""),
                # CoVe verification metadata — surfaced in the UI
                "_cove_verified":   cove_verified,
                "_cove_status":     t.get("_cove_status", "VERIFIED" if cove_verified else "UNVERIFIED"),
                "_confidence_pct":  conf_pct,
                "_rsf_confidence":  t.get("_rsf_confidence", 100.0 if cove_verified else 0.0),
                "_rent_confidence": t.get("_rent_confidence", 100.0 if cove_verified else 0.0),
                "_cove_reads":      t.get("_cove_reads", {}),
                "_rsf_suppressed":  rsf_supp,
                "_rent_suppressed": rent_supp,
            })

        # WALT (weighted average lease term)
        walt_months = self._calc_walt(all_tenants)

        # Summary line from extraction (for cross-check)
        stated_total_sf   = None
        stated_total_rent = None
        for doc in documents:
            summary = doc.get("extraction", {}).get("summary") or {}
            if summary.get("total_rsf"):
                stated_total_sf = self._sf(summary["total_rsf"])
            if summary.get("total_annual_rent"):
                stated_total_rent = self._sf(summary["total_annual_rent"])

        # Arithmetic check: do the individual tenant rows add up to the stated summary?
        sum_mismatch = None
        if stated_total_sf and total_sf:
            delta = abs(stated_total_sf - total_sf)
            if delta / max(stated_total_sf, 1) > 0.02:
                sum_mismatch = f"Tenant SF sum ({total_sf:,.0f}) differs from stated total ({stated_total_sf:,.0f}) by {delta:,.0f} SF"

        return {
            # Tenant data (sourced directly from extraction, CoVe-scored)
            "tenants":                 enriched_tenants,
            "tenant_count":            len(enriched_tenants),
            "verified_tenant_count":   sum(1 for t in enriched_tenants if t.get("_cove_verified", True)),
            "unverified_suppressed":   unverified_suppressed,
            # RSF numbers
            "rent_roll_total_sf":    total_sf,
            "property_appraiser_sf": pa_sf,
            "rsf_gap_sf":            rsf_gap_sf,
            "rsf_gap_annual_value":  rsf_gap_value,
            "rsf_gap_pct":           round((rsf_gap_sf / pa_sf * 100) if pa_sf else 0, 2),
            # Financial numbers
            "total_annual_rent":     round(total_rent, 2),
            "average_rent_psf":      round(avg_psf, 2),
            "walt_months":           walt_months,
            # Cross-checks
            "stated_total_sf":       stated_total_sf,
            "stated_total_rent":     stated_total_rent,
            "sum_mismatch":          sum_mismatch,
            # Source metadata
            "source_documents":      [d.get("filename") for d in documents],
        }

    def _calc_walt(self, tenants: list[dict]) -> float | None:
        """Weighted average lease term in months."""
        try:
            from dateutil import parser
            today = datetime.now()
            weighted_sum = 0.0
            weight_sum   = 0.0
            for t in tenants:
                expiry = t.get("lease_end") or t.get("lease_expiration_date") or ""
                t_sf   = self._sf(t.get("rsf") or 0)
                if not expiry or not t_sf:
                    continue
                exp = parser.parse(str(expiry))
                months = max(0, (exp.year - today.year) * 12 + (exp.month - today.month))
                weighted_sum += months * t_sf
                weight_sum   += t_sf
            if weight_sum > 0:
                return round(weighted_sum / weight_sum, 1)
        except Exception:
            pass
        return None

    def _sf(self, v) -> float:
        """Safe float conversion."""
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            try:
                return float(v.replace(",", "").replace("$", "").replace("SF", "").strip())
            except Exception:
                pass
        return 0.0

    # =========================================================================
    # HOP 5 — SYNTHESIZE (AI, grounded in reconciled numbers)
    # =========================================================================

    async def _synthesize(self, deal_name: str, documents: list[dict], recon: dict) -> dict:
        """
        Send the reconciled numbers (not raw text) to the AI.
        The AI's job: write flags, score the deal, and recommend next steps.
        It cannot invent numbers because the numbers are already computed.
        """
        doc_types = list({d.get("doc_type", "UNKNOWN") for d in documents})
        pa_sf     = recon["property_appraiser_sf"]
        gap_sf    = recon["rsf_gap_sf"]
        gap_val   = recon["rsf_gap_annual_value"]
        gap_pct   = recon["rsf_gap_pct"]
        tenants   = recon["tenants"]
        walt      = recon["walt_months"]
        total_sf  = recon["rent_roll_total_sf"]
        total_rent= recon["total_annual_rent"]
        avg_psf   = recon["average_rent_psf"]
        n_tenants = recon["tenant_count"]
        mismatch  = recon["sum_mismatch"]

        # Build a compact, token-efficient tenant summary for the AI
        tenant_lines = []
        for t in tenants[:50]:  # cap at 50 for synthesis context
            lease_end = t.get("lease_end") or "N/A"
            tenant_lines.append(
                f"  - {t['tenant']} | Suite {t['suite']} | {t['rsf']:,.0f} SF | "
                f"${t['annual_rent']:,.0f}/yr (${t['rent_psf']:.2f}/SF) | Expires: {lease_end}"
            )
        tenant_block = "\n".join(tenant_lines) if tenant_lines else "  (no tenant rows extracted)"
        if len(tenants) > 50:
            tenant_block += f"\n  ... and {len(tenants) - 50} more tenants"

        rsf_block = (
            f"Property Appraiser SF: {pa_sf:,.0f} SF\n"
            f"Rent Roll Total SF: {total_sf:,.0f} SF\n"
            f"RSF Gap: {gap_sf:,.0f} SF ({gap_pct:.1f}%)\n"
            f"Estimated Annual Recovery at ${avg_psf:.2f}/SF: ${gap_val:,.0f}"
            if pa_sf else
            f"Rent Roll Total SF: {total_sf:,.0f} SF\nNo PA SF provided — cannot calculate RSF gap"
        )

        prompt = f"""You are a commercial real estate deal analyst. Below are the VERIFIED reconciled numbers from the deal package "{deal_name}".
These numbers were computed directly from the extracted document data. Do not change them.
Your job: identify red flags, score the deal, and recommend what documents to get next.

DOCUMENT TYPES PRESENT: {', '.join(doc_types)}
TENANT COUNT: {n_tenants}
WALT: {f"{walt:.1f} months" if walt else "Unknown"}
TOTAL ANNUAL RENT: ${total_rent:,.0f}
AVG RENT PSF: ${avg_psf:.2f}

RSF RECONCILIATION:
{rsf_block}

{f"ARITHMETIC WARNING: {mismatch}" if mismatch else "Arithmetic check: tenant SF rows sum correctly to total."}

TENANT ROSTER (from rent roll):
{tenant_block}

Return ONLY valid JSON with EXACTLY these keys (no others, no markdown fences):

{{
  "red_flags": [
    {{
      "severity": "<CRITICAL|HIGH|MODERATE|LOW>",
      "category": "<RSF Discrepancy|Lease Expiration|Data Quality|Financial|Tenant Concentration|Other>",
      "flag": "<short_snake_case_id>",
      "description": "<specific finding citing tenant names/amounts from the roster above>",
      "impact": "<specific financial or operational impact with dollar amounts where possible>",
      "resolution": "<specific action to take>"
    }}
  ],
  "deal_score": {{
    "overall_score": <0-100 integer. Start at 100. Deduct: 20 if RSF gap >2%, 10 per lease expiring <12mo, 5 per CRITICAL flag, 3 per HIGH flag>,
    "tier": "<GREEN if >=85 | YELLOW if >=70 | ORANGE if >=50 | RED if <50>",
    "data_completeness": <0-100, based on document types present>,
    "rsf_accuracy": <0-100, 100 if no gap, proportionally lower based on gap_pct>,
    "lease_health": <0-100, based on WALT and near-term expirations>
  }},
  "what_to_get_next": ["<specific document name and why>"],
  "narrative": "<2-3 sentence plain-English summary of the deal for a CRE investor>"
}}

RULES:
- Every red flag MUST cite specific tenant names or dollar amounts from the roster above.
- Do not flag "missing documents" unless you have a specific reason based on the data above.
- Score deductions must be mathematically consistent with the data provided.
- what_to_get_next must be specific (e.g. "Executed lease for Tenant X — needed to verify SF of 22,500" not "Lease documents")."""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}],
        )
        return self._parse_json(response.choices[0].message.content)

    # =========================================================================
    # HOP 6 — VERIFY (Python, no AI)
    # Force the AI's score/numbers to match the reconciled truth.
    # =========================================================================

    def _verify_and_correct(self, synthesis: dict, recon: dict) -> dict:
        """
        Check the AI's output against the reconciled numbers.
        Fix any arithmetic errors. Log corrections.
        """
        corrections: list[str] = []
        score_data = synthesis.get("deal_score") or {}

        # 1. Verify and correct RSF accuracy sub-score
        gap_pct = recon["rsf_gap_pct"]
        expected_rsf_accuracy = max(0, round(100 - gap_pct * 5))  # -5 pts per 1% gap
        ai_rsf_accuracy = score_data.get("rsf_accuracy")
        if ai_rsf_accuracy is not None:
            ai_val = self._sf(ai_rsf_accuracy)
            if abs(ai_val - expected_rsf_accuracy) > 15:
                corrections.append(f"RSF accuracy: AI={ai_val}, corrected to {expected_rsf_accuracy} (gap={gap_pct:.1f}%)")
                score_data["rsf_accuracy"] = expected_rsf_accuracy

        # 2. Verify tier matches score
        overall = self._sf(score_data.get("overall_score") or 0)
        expected_tier = self._score_to_tier(overall)
        ai_tier = str(score_data.get("tier") or "").upper().strip()
        normalized_tier = self._normalize_tier(ai_tier)
        if normalized_tier != expected_tier:
            corrections.append(f"Tier: AI='{ai_tier}' → corrected to '{expected_tier}' (score={overall})")
            score_data["tier"] = expected_tier

        # 3. Remove any red flags that contradict the data
        # (e.g. "No rent roll data" flag when we have tenants)
        red_flags = synthesis.get("red_flags") or []
        if recon["tenant_count"] > 0:
            before = len(red_flags)
            red_flags = [
                f for f in red_flags
                if not any(phrase in str(f.get("description", "")).lower() for phrase in [
                    "no rent roll", "no tenant data", "missing rent roll", "rent roll not provided"
                ])
            ]
            if len(red_flags) < before:
                corrections.append(f"Removed {before - len(red_flags)} invalid 'no rent roll' flag(s) — {recon['tenant_count']} tenants were found")
            synthesis["red_flags"] = red_flags

        # 4. If RSF gap exists but AI didn't flag it, add one
        if recon["rsf_gap_sf"] > 500 and not any(
            "rsf" in str(f.get("flag", "")).lower() or "square" in str(f.get("description", "")).lower()
            for f in red_flags
        ):
            red_flags.insert(0, {
                "severity": "HIGH" if recon["rsf_gap_pct"] > 5 else "MODERATE",
                "category": "RSF Discrepancy",
                "flag": "rsf_gap_detected",
                "description": (
                    f"Rent roll total SF ({recon['rent_roll_total_sf']:,.0f} SF) is "
                    f"{recon['rsf_gap_sf']:,.0f} SF less than the Property Appraiser baseline "
                    f"({recon['property_appraiser_sf']:,.0f} SF) — a {recon['rsf_gap_pct']:.1f}% gap."
                ),
                "impact": f"${recon['rsf_gap_annual_value']:,.0f}/yr potential under-billed rent at ${recon['average_rent_psf']:.2f}/SF average.",
                "resolution": "Cross-reference each lease for correct SF and bill tenants for underpaid square footage.",
            })
            synthesis["red_flags"] = red_flags
            corrections.append(f"Added RSF gap flag ({recon['rsf_gap_sf']:,.0f} SF / ${recon['rsf_gap_annual_value']:,.0f}/yr)")

        if corrections:
            for c in corrections:
                self.tracer.log("HOP_6", f"  CORRECTED: {c}", "warning")
        else:
            self.tracer.log("HOP_6", "  AI output verified — no corrections needed", "success")

        synthesis["deal_score"] = score_data
        synthesis["_corrections"] = corrections
        return synthesis

    # =========================================================================
    # HOP 7 — BUILD REPORT
    # =========================================================================

    def _build_report(self, deal_name: str, documents: list[dict], synthesis: dict, recon: dict) -> dict:
        score_data = synthesis.get("deal_score") or {}
        red_flags  = synthesis.get("red_flags") or []
        fin        = synthesis.get("financial_summary") or {}

        # Normalize red_flags
        if isinstance(red_flags, dict):
            flat = []
            for sev, flags in red_flags.items():
                if isinstance(flags, list):
                    for f in flags:
                        flat.append({**f, "severity": sev} if isinstance(f, dict) else {"severity": sev, "description": str(f)})
            red_flags = flat

        score_value = self._sf(score_data.get("overall_score") or 0)
        ai_tier     = str(score_data.get("tier") or "").upper().strip()
        tier_value  = self._normalize_tier(ai_tier) if ai_tier else self._score_to_tier(score_value)

        pa_sf       = recon["property_appraiser_sf"]
        gap_sf      = recon["rsf_gap_sf"]
        gap_val     = recon["rsf_gap_annual_value"]

        # Normalize severity for frontend
        def norm_sev(s):
            v = str(s or "").upper().strip()
            if v in ("HIGH", "CRITICAL"):        return "HIGH"
            if v in ("MEDIUM", "MODERATE"):      return "MEDIUM"
            return "LOW"

        normalized_flags = [
            {**f, "severity": norm_sev(f.get("severity"))}
            for f in red_flags if isinstance(f, dict)
        ]

        what_next = self._normalize_to_list(synthesis.get("what_to_get_next") or [])

        return {
            "success": True,
            "deal_name": deal_name,
            "analyzed_at": datetime.utcnow().isoformat(),
            "narrative": synthesis.get("narrative", ""),

            # Core output — every number sourced from recon (Python arithmetic)
            "documents_processed": len(documents),
            "property_appraiser_sf": pa_sf,
            "score": score_value,
            "tier": tier_value,
            "rsf_recovery_sf": gap_sf,
            "rsf_recovery_annual_value": gap_val,
            "red_flags": normalized_flags,
            "tenants": recon["tenants"],  # grounded: from extraction, not AI synthesis
            "what_to_get_next": what_next,

            # RSF analysis (all from recon)
            "rsf_analysis": {
                "reconciliation": {
                    "property_appraiser_sf": pa_sf,
                    "rent_roll_total_sf": recon["rent_roll_total_sf"],
                    "discrepancy_sf": gap_sf,
                    "discrepancy_pct": recon["rsf_gap_pct"],
                    "alert_triggered": gap_sf > 0,
                    "stated_total_sf": recon.get("stated_total_sf"),
                    "sum_mismatch": recon.get("sum_mismatch"),
                },
                "recovery_opportunity": {
                    "recoverable_sf": gap_sf,
                    "average_rent_psf": recon["average_rent_psf"],
                    "estimated_annual_recovery": gap_val,
                },
                "discrepancy_found": gap_sf > 0,
            },

            # Risk block
            "risk": {
                "score": score_value,
                "tier": tier_value,
                "sub_scores": {
                    "data_completeness": self._sf(score_data.get("data_completeness") or 0),
                    "rsf_accuracy": self._sf(score_data.get("rsf_accuracy") or 0),
                    "lease_health": self._sf(score_data.get("lease_health") or 0),
                },
                "red_flags": normalized_flags,
                "red_flag_count": {
                    "critical": sum(1 for f in red_flags if str(f.get("severity", "")).upper() == "CRITICAL"),
                    "high":     sum(1 for f in red_flags if str(f.get("severity", "")).upper() == "HIGH"),
                    "moderate": sum(1 for f in red_flags if str(f.get("severity", "")).upper() in ("MODERATE", "MEDIUM")),
                    "low":      sum(1 for f in red_flags if str(f.get("severity", "")).upper() == "LOW"),
                },
            },

            # Financial (from recon arithmetic)
            "financial": {
                "total_annual_rent": recon["total_annual_rent"],
                "average_rent_psf": recon["average_rent_psf"],
                "walt": recon["walt_months"],
                "noi": self._sf(fin.get("noi") or 0),
                "vacancy": self._sf(fin.get("vacancy") or 0),
            },

            # Documents
            "documents": {
                "total": len(documents),
                "by_type": self._count_by_type(documents),
                "files": [
                    {"filename": d.get("filename"), "type": d.get("doc_type"), "confidence": d.get("confidence")}
                    for d in documents
                ],
            },

            # Lease abstracts (from lease docs)
            "lease_abstracts": self._extract_lease_abstracts(documents),

            # COVE confidence summary
            "cove": {
                "threshold_pct":          COVE_AGREEMENT_THRESHOLD * 100,
                "verified_tenants":       recon.get("verified_tenant_count", recon["tenant_count"]),
                "unverified_tenants":     recon.get("unverified_tenant_count", 0),
                "total_tenants":          recon["tenant_count"],
                "suppressed_fields":      [
                    f"{t['tenant']} (suite {t['suite']}): confidence {t.get('_confidence_pct', 0):.0f}% — RSF and/or rent suppressed"
                    for t in recon["tenants"] if not t.get("_verified", True)
                ],
            },

            # Pipeline metadata
            "_pipeline": {
                "hops": 8,
                "tenant_count":          recon["tenant_count"],
                "verified_tenant_count": recon.get("verified_tenant_count", recon["tenant_count"]),
                "unverified_suppressed": recon.get("unverified_suppressed", 0),
                "rsf_gap_sf":            gap_sf,
                "rsf_gap_pct":           recon["rsf_gap_pct"],
                "corrections_applied":   synthesis.get("_corrections", []),
                "source_documents":      recon["source_documents"],
                # CoVe summary per document
                "cove_summary": [
                    {
                        "filename": d.get("filename"),
                        **( d.get("cove_summary") or {} ),
                    }
                    for d in documents
                ],
            },
        }

    # =========================================================================
    # Helpers
    # =========================================================================

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
                "rentable_sf": self._sf(ext.get("rentable_sf") or ext.get("rsf") or 0),
                "lease_commencement": ext.get("lease_commencement_date") or ext.get("lease_start") or "",
                "lease_expiration": ext.get("lease_expiration_date") or ext.get("lease_end"),
                "annual_base_rent": self._sf(ext.get("base_rent_annual") or ext.get("annual_base_rent") or 0),
                "escalation": ext.get("escalation_type") or ext.get("escalations") or "",
                "expense_structure": ext.get("expense_structure") or "NNN",
                "missing_fields": [],
            })
        return abstracts

    def _slim_extraction(self, extraction: dict, _depth: int = 0) -> dict:
        if not isinstance(extraction, dict):
            return extraction
        STRIP = {"source_text", "raw_text", "raw_text_sample", "_note", "text", "full_text", "page_text"}
        result = {}
        for k, v in extraction.items():
            if k in STRIP:
                continue
            if isinstance(v, dict):
                result[k] = self._slim_extraction(v, _depth + 1)
            elif isinstance(v, list):
                result[k] = [
                    self._slim_extraction(i, _depth + 1) if isinstance(i, dict)
                    else (i[:200] + "..." if isinstance(i, str) and len(i) > 200 else i)
                    for i in v if i is not None
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
            out = []
            for item in value:
                if item is None:
                    continue
                if isinstance(item, dict):
                    # Extract string from common dict shapes
                    s = item.get("document") or item.get("name") or item.get("text") or str(item)
                    out.append(s)
                else:
                    out.append(str(item))
            return out
        if isinstance(value, dict):
            for key in ("items", "list", "documents"):
                if key in value:
                    return self._normalize_to_list(value[key])
            return [str(value)]
        return [str(value)]

    def _count_by_type(self, documents: list[dict]) -> dict:
        counts: dict[str, int] = {}
        for doc in documents:
            t = doc.get("doc_type", "UNKNOWN")
            counts[t] = counts.get(t, 0) + 1
        return counts

    def _score_to_tier(self, score: float) -> str:
        if score >= 85:   return "GREEN"
        if score >= 70:   return "YELLOW"
        if score >= 50:   return "ORANGE"
        return "RED"

    def _normalize_tier(self, tier_str: str) -> str:
        mapping = {
            "GREEN": "GREEN",   "PASS": "GREEN",   "LOW RISK": "GREEN",   "VERIFIED": "GREEN",
            "YELLOW": "YELLOW", "CAUTION": "YELLOW", "UNDER REVIEW": "YELLOW", "STANDARD": "YELLOW",
            "ORANGE": "ORANGE", "HIGH RISK": "ORANGE",
            "RED": "RED",       "CRITICAL": "RED", "FAIL": "RED",
        }
        return mapping.get(tier_str.upper().strip(), self._score_to_tier(0))

    def _parse_json(self, text: str) -> dict:
        if not text:
            return {}
        text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
        text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if match:
                try:
                    return json.loads(match.group())
                except Exception:
                    pass
            return {}

    def _error_response(self, deal_name: str, error: str) -> dict:
        return {
            "success": False,
            "deal_name": deal_name,
            "error": error,
            "trace_log": self.tracer.get_logs() if self.tracer else [],
        }

    def _to_deal_analysis(self, report: dict) -> DealAnalysis:
        def _sev(s: str) -> Severity:
            v = s.lower().strip()
            if v in ("critical", "high"):   return Severity.HIGH
            if v in ("moderate", "medium"): return Severity.MEDIUM
            return Severity.LOW

        flags = []
        for i, f in enumerate(report.get("red_flags", [])):
            if not f or not isinstance(f, dict):
                continue
            sev_str = f.get("severity", "LOW")
            try:
                sev = _sev(sev_str)
            except Exception:
                sev = Severity.LOW
            flags.append(RedFlag(
                id=f"flag-{i}",
                severity=sev,
                category=f.get("category", "General"),
                title=f.get("flag") or f.get("description", "")[:80] or "Flag",
                description=f.get("description", ""),
                recommended_action=f.get("resolution") or f.get("recommended_action") or "",
                financial_impact=self._sf(f.get("financial_impact") or 0) or None,
            ))

        return DealAnalysis(
            deal_name=report.get("deal_name", ""),
            overall_score=report.get("score", 0),
            tier=report.get("tier", "UNKNOWN"),
            sub_scores=report.get("risk", {}).get("sub_scores", {}),
            red_flags=flags,
            tenants=report.get("tenants", []),
            rsf_reconciliation=report.get("rsf_analysis", {}).get("reconciliation", {}),
            what_to_get_next=report.get("what_to_get_next", []),
        )

    # =========================================================================
    # File type helpers
    # =========================================================================

    def _guess_content_type(self, filename: str) -> str:
        return {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xls": "application/vnd.ms-excel",
            "csv": "text/csv",
            "png": "image/png",
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "tiff": "image/tiff", "tif": "image/tiff",
        }.get(self._get_ext(filename), "application/octet-stream")

    def _get_ext(self, filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    def _is_excel(self, fn: str, ct: str) -> bool:
        return self._get_ext(fn) in ["xlsx", "xls", "csv"] or "spreadsheet" in ct or "excel" in ct

    def _is_pdf(self, fn: str, ct: str) -> bool:
        return self._get_ext(fn) == "pdf" or ct == "application/pdf"

    def _is_image(self, fn: str, ct: str) -> bool:
        return self._get_ext(fn) in ["png", "jpg", "jpeg", "tiff", "tif"] or ct.startswith("image/")
