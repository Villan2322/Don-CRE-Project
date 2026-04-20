"""
CRE Document Intelligence Pipeline - Adaptive Document Processing

This pipeline is fully adaptive:
1. Upload ANY document(s) - no need to specify count or type
2. Auto-detects file type (PDF, Excel, image)
3. Auto-determines if OCR is needed (scanned vs text PDF)
4. Auto-classifies document type using AI
5. Extracts relevant data based on classification
6. Synthesizes analysis from whatever docs are available
7. Outputs report showing RSF discrepancies and recovery opportunities

The goal: Help Don identify properties underpaying on square footage.
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
    SYNTHESIS_PROMPT,
    VERIFICATION_PROMPT,
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


class CREPipeline:
    """
    Adaptive CRE Document Intelligence Pipeline.
    
    Just upload files - the pipeline figures out everything else.
    """
    
    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""),
        )
        self.model = "anthropic/claude-sonnet-4"
    
    # =========================================================================
    # MAIN ENTRY POINT - Just pass files, get analysis
    # =========================================================================
    
    async def analyze(self, files: list[dict], deal_name: str = None) -> dict:
        """
        Main entry point - analyze any uploaded documents.
        
        Args:
            files: List of file dicts, each with:
                - filename: Original filename
                - content: File content (text for PDFs, base64 for images/excel)
                - content_type: MIME type (optional, will auto-detect)
            deal_name: Optional name for this analysis (auto-generated if not provided)
            
        Returns:
            Complete analysis report with RSF discrepancies and recommendations
        """
        if not deal_name:
            deal_name = f"Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Stage 1: Ingest and prepare all files
        documents = await self._ingest_files(files)
        
        if not documents:
            return {
                "success": False,
                "deal_name": deal_name,
                "error": "No processable documents found",
                "documents_received": len(files),
            }
        
        # Stage 2: Classify each document
        classified = await self._classify_all(documents)
        
        # Stage 3: Extract data from each document
        extracted = await self._extract_all(classified)
        
        # Stage 4: Synthesize cross-document analysis
        synthesis = await self._synthesize(deal_name, extracted)
        
        # Stage 5: Build final report
        report = self._build_report(deal_name, extracted, synthesis)
        
        return report
    
    # Alias for backwards compatibility
    async def run(self, deal_name: str, documents: list[dict]) -> DealAnalysis:
        """Legacy interface - wraps analyze()."""
        result = await self.analyze(documents, deal_name)
        return self._to_deal_analysis(result)
    
    # =========================================================================
    # STAGE 1: File Ingestion - Auto-detect type and extract text
    # =========================================================================
    
    async def _ingest_files(self, files: list[dict]) -> list[dict]:
        """
        Ingest any files - auto-detect type, OCR if needed, extract text.
        """
        documents = []
        
        for i, file in enumerate(files):
            filename = file.get("filename", f"document_{i}")
            content = file.get("content", "")
            content_type = file.get("content_type", self._guess_content_type(filename))
            
            doc = {
                "id": f"doc_{i}",
                "filename": filename,
                "content_type": content_type,
                "file_ext": self._get_ext(filename),
                "ingested_at": datetime.utcnow().isoformat(),
            }
            
            # Extract text based on file type
            if self._is_excel(filename, content_type):
                doc["text"] = await self._extract_excel_text(content, filename)
                doc["source_type"] = "excel"
            elif self._is_pdf(filename, content_type):
                text = self._extract_pdf_text(content)
                if len(text.strip()) < 100:
                    # Likely scanned - needs OCR
                    doc["text"] = await self._ocr_document(content, filename)
                    doc["source_type"] = "pdf_ocr"
                else:
                    doc["text"] = text
                    doc["source_type"] = "pdf_text"
            elif self._is_image(filename, content_type):
                doc["text"] = await self._ocr_document(content, filename)
                doc["source_type"] = "image_ocr"
            else:
                # Assume it's already text
                doc["text"] = content if isinstance(content, str) else str(content)
                doc["source_type"] = "text"
            
            # Only include if we got meaningful text
            if doc.get("text") and len(doc["text"].strip()) > 50:
                doc["char_count"] = len(doc["text"])
                documents.append(doc)
        
        return documents
    
    def _guess_content_type(self, filename: str) -> str:
        """Guess MIME type from filename."""
        ext = self._get_ext(filename)
        types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xls": "application/vnd.ms-excel",
            "csv": "text/csv",
            "png": "image/png",
            "jpg": "image/jpeg",
            "jpeg": "image/jpeg",
            "tiff": "image/tiff",
            "tif": "image/tiff",
        }
        return types.get(ext, "application/octet-stream")
    
    def _get_ext(self, filename: str) -> str:
        return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    def _is_excel(self, filename: str, content_type: str) -> bool:
        ext = self._get_ext(filename)
        return ext in ["xlsx", "xls", "csv"] or "spreadsheet" in content_type or "excel" in content_type
    
    def _is_pdf(self, filename: str, content_type: str) -> bool:
        return self._get_ext(filename) == "pdf" or content_type == "application/pdf"
    
    def _is_image(self, filename: str, content_type: str) -> bool:
        ext = self._get_ext(filename)
        return ext in ["png", "jpg", "jpeg", "tiff", "tif"] or content_type.startswith("image/")
    
    def _extract_pdf_text(self, content: str | bytes) -> str:
        """Extract text from PDF using PyPDF2."""
        try:
            from PyPDF2 import PdfReader
            
            if isinstance(content, str):
                # Might be base64 encoded
                try:
                    content = base64.b64decode(content)
                except:
                    return content  # Already text
            
            pdf = PdfReader(io.BytesIO(content))
            text_parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return "\n\n".join(text_parts)
        except Exception as e:
            return f"[PDF extraction error: {e}]"
    
    async def _extract_excel_text(self, content: str | bytes, filename: str) -> str:
        """Extract text representation from Excel file."""
        try:
            import pandas as pd
            
            if isinstance(content, str):
                try:
                    content = base64.b64decode(content)
                except:
                    return content
            
            # Read all sheets
            excel_file = pd.ExcelFile(io.BytesIO(content))
            text_parts = []
            
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                text_parts.append(f"=== Sheet: {sheet_name} ===")
                text_parts.append(df.to_string())
            
            return "\n\n".join(text_parts)
        except Exception as e:
            return f"[Excel extraction error: {e}]"
    
    async def _ocr_document(self, content: str | bytes, filename: str) -> str:
        """
        OCR a scanned document or image using Claude's vision.
        """
        try:
            if isinstance(content, bytes):
                b64_content = base64.b64encode(content).decode("utf-8")
            else:
                b64_content = content
            
            # Determine media type
            ext = self._get_ext(filename)
            media_types = {
                "pdf": "application/pdf",
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "tiff": "image/tiff",
            }
            media_type = media_types.get(ext, "image/png")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=8000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64_content,
                                }
                            },
                            {
                                "type": "text",
                                "text": "Extract ALL text from this document. Preserve the structure including tables, columns, and formatting. Return only the extracted text, no commentary."
                            }
                        ]
                    }
                ],
            )
            
            return response.choices[0].message.content
        except Exception as e:
            return f"[OCR error: {e}]"
    
    # =========================================================================
    # STAGE 2: Classification - What type of document is this?
    # =========================================================================
    
    async def _classify_all(self, documents: list[dict]) -> list[dict]:
        """Classify all documents in parallel."""
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
        """Classify a single document."""
        # Sample beginning and end for better classification
        text = doc.get("text", "")
        sample = text[:2000]
        if len(text) > 4000:
            sample += "\n\n[...middle truncated...]\n\n" + text[-2000:]
        
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {
                    "role": "user",
                    "content": f"Filename: {doc.get('filename', 'unknown')}\n\nDocument text:\n{sample}"
                },
            ],
        )
        
        result = self._parse_json(response.choices[0].message.content)
        
        return {
            "doc_type": result.get("doc_type", "UNKNOWN"),
            "confidence": result.get("confidence", 0.5),
            "reasoning": result.get("reasoning", ""),
        }
    
    # =========================================================================
    # STAGE 3: Extraction - Pull structured data based on doc type
    # =========================================================================
    
    async def _extract_all(self, documents: list[dict]) -> list[dict]:
        """Extract data from all documents in parallel."""
        tasks = [self._extract_one(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                doc["extraction"] = {"error": str(result)}
            else:
                doc["extraction"] = result
                
            # Enrich lease documents
            if doc.get("doc_type") in ["LEASE", "LEASE_ABSTRACT"]:
                self._enrich_lease(doc)
        
        return documents
    
    async def _extract_one(self, doc: dict) -> dict:
        """Extract structured data from one document."""
        doc_type = doc.get("doc_type", "UNKNOWN")
        
        # Get config for this doc type
        config = EXTRACTION_PROMPTS.get(doc_type)
        if not config:
            return {"_note": f"No extraction config for {doc_type}", "raw_text_sample": doc.get("text", "")[:500]}
        
        text = doc.get("text", "")
        # Truncate to avoid token limits
        if len(text) > 40000:
            text = text[:20000] + "\n\n[...truncated...]\n\n" + text[-20000:]
        
        prompt = f"""Extract the following fields from this {doc_type} document.

Fields to extract: {', '.join(config.get('fields', []))}

Document:
{text}

Return JSON with each field. Include the extracted value, or null if not found.
For numeric values (SF, rent, etc), extract just the number without formatting."""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": config.get("system", "You are a CRE document analyst.")},
                {"role": "user", "content": prompt},
            ],
        )
        
        return self._parse_json(response.choices[0].message.content)
    
    def _enrich_lease(self, doc: dict):
        """Add calculated fields to lease extractions."""
        ext = doc.get("extraction", {})
        
        # Calculate months remaining
        expiry = ext.get("lease_expiration_date") or ext.get("expiration_date")
        months_remaining = None
        risk_level = "UNKNOWN"
        
        if expiry:
            try:
                from dateutil import parser
                exp_date = parser.parse(str(expiry))
                today = datetime.now()
                months_remaining = (exp_date.year - today.year) * 12 + (exp_date.month - today.month)
                
                if months_remaining <= 0:
                    risk_level = "EXPIRED"
                elif months_remaining <= 6:
                    risk_level = "CRITICAL"
                elif months_remaining <= 12:
                    risk_level = "HIGH"
                elif months_remaining <= 24:
                    risk_level = "MODERATE"
                else:
                    risk_level = "LOW"
            except:
                pass
        
        doc["enriched"] = {
            "months_remaining": months_remaining,
            "risk_level": risk_level,
        }
    
    # =========================================================================
    # STAGE 4: Synthesis - Cross-document analysis
    # =========================================================================
    
    async def _synthesize(self, deal_name: str, documents: list[dict]) -> dict:
        """
        Synthesize all extracted data into a comprehensive analysis.
        Focus: RSF discrepancies and recovery opportunities.
        """
        # Group docs by type
        by_type = {}
        for doc in documents:
            dtype = doc.get("doc_type", "UNKNOWN")
            if dtype not in by_type:
                by_type[dtype] = []
            by_type[dtype].append({
                "filename": doc.get("filename"),
                "extraction": doc.get("extraction", {}),
                "enriched": doc.get("enriched", {}),
            })
        
        # Build summary for synthesis
        summary = {
            "deal_name": deal_name,
            "document_types_present": list(by_type.keys()),
            "document_count": len(documents),
            "documents_by_type": {k: len(v) for k, v in by_type.items()},
            "extractions": by_type,
        }
        
        prompt = f"""Analyze this CRE deal package and produce a comprehensive report.

CRITICAL FOCUS: Identify RSF (rentable square footage) discrepancies between sources.
Don needs to find properties that may be underpaying based on incorrect SF.

Deal Package:
{json.dumps(summary, indent=2, default=str)}

Produce analysis with these sections:

1. RSF_RECONCILIATION
   - Compare SF from: rent roll, leases, BOMA measurement, county PA records
   - Calculate discrepancy_sf (difference between highest and lowest)
   - Calculate discrepancy_pct
   - Identify which tenants have SF mismatches

2. RSF_RECOVERY_OPPORTUNITY
   - If discrepancies exist, calculate potential annual revenue recovery
   - Use formula: discrepancy_sf * average_rent_psf
   - Flag tenants who may be underpaying

3. TENANT_ANALYSIS
   - List all tenants with their SF from each source
   - Flag any with >2% variance across sources
   - Include lease expiry and risk level

4. RED_FLAGS
   - List issues by severity: CRITICAL, HIGH, MODERATE, LOW
   - Include: SF discrepancies, lease expirations, missing docs, calculation errors

5. DEAL_SCORE
   - Score 0-100 based on data quality and risk
   - Sub-scores for: data_completeness, rsf_accuracy, lease_health, financial_clarity

6. WHAT_TO_GET_NEXT
   - Prioritized list of missing documents that would improve analysis
   - Focus on docs that would resolve SF discrepancies

7. FINANCIAL_SUMMARY
   - NOI, total rent, vacancy, WALT if calculable from available docs

Return as JSON with these exact top-level keys."""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": SYNTHESIS_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        
        return self._parse_json(response.choices[0].message.content)
    
    # =========================================================================
    # STAGE 5: Build Final Report
    # =========================================================================
    
    def _build_report(self, deal_name: str, documents: list[dict], synthesis: dict) -> dict:
        """
        Build the final report that Don can use.
        """
        # Extract key metrics
        rsf_recon = synthesis.get("RSF_RECONCILIATION", synthesis.get("rsf_reconciliation", {}))
        recovery = synthesis.get("RSF_RECOVERY_OPPORTUNITY", synthesis.get("rsf_recovery_opportunity", {}))
        red_flags = synthesis.get("RED_FLAGS", synthesis.get("red_flags", []))
        score_data = synthesis.get("DEAL_SCORE", synthesis.get("deal_score", {}))
        
        # Normalize red flags to list
        if isinstance(red_flags, dict):
            flat_flags = []
            for severity, flags in red_flags.items():
                if isinstance(flags, list):
                    for f in flags:
                        if isinstance(f, str):
                            flat_flags.append({"severity": severity, "message": f})
                        else:
                            flat_flags.append({**f, "severity": severity})
            red_flags = flat_flags
        
        return {
            "success": True,
            "deal_name": deal_name,
            "analyzed_at": datetime.utcnow().isoformat(),
            
            # Document summary
            "documents": {
                "total": len(documents),
                "by_type": self._count_by_type(documents),
                "files": [
                    {
                        "filename": d.get("filename"),
                        "type": d.get("doc_type"),
                        "confidence": d.get("confidence"),
                    }
                    for d in documents
                ],
            },
            
            # RSF Analysis - THE KEY OUTPUT
            "rsf_analysis": {
                "reconciliation": rsf_recon,
                "recovery_opportunity": recovery,
                "discrepancy_found": bool(rsf_recon.get("discrepancy_sf", 0)),
            },
            
            # Risk assessment
            "risk": {
                "score": score_data.get("score", score_data.get("overall", 0)),
                "tier": self._score_to_tier(score_data.get("score", score_data.get("overall", 0))),
                "sub_scores": score_data.get("sub_scores", {}),
                "red_flags": red_flags,
                "red_flag_count": {
                    "critical": len([f for f in red_flags if f.get("severity") == "CRITICAL"]),
                    "high": len([f for f in red_flags if f.get("severity") == "HIGH"]),
                    "moderate": len([f for f in red_flags if f.get("severity") == "MODERATE"]),
                    "low": len([f for f in red_flags if f.get("severity") == "LOW"]),
                },
            },
            
            # Tenants - ensure it's always a list
            "tenants": self._normalize_to_list(
                synthesis.get("TENANT_ANALYSIS", synthesis.get("tenant_analysis", []))
            ),
            
            # Financial
            "financial": synthesis.get("FINANCIAL_SUMMARY", synthesis.get("financial_summary", {})),
            
            # Next steps - ensure it's always a list
            "what_to_get_next": self._normalize_to_list(
                synthesis.get("WHAT_TO_GET_NEXT", synthesis.get("what_to_get_next", []))
            ),
            
            # Full synthesis for reference
            "_raw_synthesis": synthesis,
        }
    
    def _count_by_type(self, documents: list[dict]) -> dict:
        counts = {}
        for doc in documents:
            dtype = doc.get("doc_type", "UNKNOWN")
            counts[dtype] = counts.get(dtype, 0) + 1
        return counts
    
    def _score_to_tier(self, score: float) -> str:
        if score >= 85:
            return "GREEN"
        elif score >= 70:
            return "YELLOW"
        elif score >= 50:
            return "ORANGE"
        else:
            return "RED"
    
    def _normalize_to_list(self, value) -> list:
        """Ensure a value is always a list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            # If it's a dict with items, try to extract them
            if "tenants" in value:
                return self._normalize_to_list(value["tenants"])
            if "items" in value:
                return self._normalize_to_list(value["items"])
            # Return as single-item list or extract values
            return list(value.values()) if value else []
        return [value]
    
    def _to_deal_analysis(self, report: dict) -> DealAnalysis:
        """Convert report dict to DealAnalysis model."""
        return DealAnalysis(
            deal_name=report.get("deal_name", ""),
            overall_score=report.get("risk", {}).get("score", 0),
            tier=report.get("risk", {}).get("tier", "UNKNOWN"),
            sub_scores=report.get("risk", {}).get("sub_scores", {}),
            red_flags=[
                RedFlag(
                    severity=Severity(f.get("severity", "LOW")),
                    category=f.get("category", "GENERAL"),
                    message=f.get("message", ""),
                    recommendation=f.get("recommendation", ""),
                )
                for f in report.get("risk", {}).get("red_flags", [])
            ],
            rsf_reconciliation=RSFReconciliation(
                rent_roll_rsf=report.get("rsf_analysis", {}).get("reconciliation", {}).get("rent_roll_rsf"),
                lease_rsf=report.get("rsf_analysis", {}).get("reconciliation", {}).get("lease_rsf"),
                boma_rsf=report.get("rsf_analysis", {}).get("reconciliation", {}).get("boma_rsf"),
                county_pa_rsf=report.get("rsf_analysis", {}).get("reconciliation", {}).get("county_pa_rsf"),
                discrepancy_sf=report.get("rsf_analysis", {}).get("reconciliation", {}).get("discrepancy_sf"),
                discrepancy_pct=report.get("rsf_analysis", {}).get("reconciliation", {}).get("discrepancy_pct"),
            ),
            rsf_recovery_sf=report.get("rsf_analysis", {}).get("recovery_opportunity", {}).get("sf", 0),
            rsf_recovery_annual_value=report.get("rsf_analysis", {}).get("recovery_opportunity", {}).get("annual_value", 0),
            what_to_get_next=report.get("what_to_get_next", []),
            analysis_timestamp=report.get("analyzed_at", ""),
            documents_processed=report.get("documents", {}).get("total", 0),
        )
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def _parse_json(self, text: str) -> dict:
        """Extract JSON from LLM response."""
        # Try to find JSON in code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if json_match:
            text = json_match.group(1)
        
        # Try to parse directly
        try:
            return json.loads(text.strip())
        except:
            pass
        
        # Try to find JSON object
        try:
            start = text.find('{')
            end = text.rfind('}') + 1
            if start >= 0 and end > start:
                return json.loads(text[start:end])
        except:
            pass
        
        return {"_raw": text, "_parse_error": True}
