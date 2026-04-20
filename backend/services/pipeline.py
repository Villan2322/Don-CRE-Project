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


class PipelineTracer:
    """Simple tracing for pipeline execution."""
    
    def __init__(self):
        self.logs = []
    
    def log(self, stage: str, message: str, level: str = "info", data: dict = None):
        """Add a trace log entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "message": message,
            "level": level,  # info, success, warning, error
        }
        if data:
            entry["data"] = data
        self.logs.append(entry)
    
    def get_logs(self) -> list[dict]:
        return self.logs


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
        self.tracer = None  # Created fresh for each analysis run
    
    # =========================================================================
    # MAIN ENTRY POINT - Just pass files, get analysis
    # =========================================================================
    
    async def analyze(self, files: list[dict], deal_name: str = None, property_appraiser_sf: float = None) -> dict:
        """
        Main entry point - analyze any uploaded documents.
        
        Args:
            files: List of file dicts, each with:
                - filename: Original filename
                - content: File content (text for PDFs, base64 for images/excel)
                - content_type: MIME type (optional, will auto-detect)
            deal_name: Optional name for this analysis (auto-generated if not provided)
            property_appraiser_sf: Official SF from County Property Appraiser - the baseline for RSF comparison
            
        Returns:
            Complete analysis report with RSF discrepancies and recommendations
        """
        if not deal_name:
            deal_name = f"Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Initialize tracer for this run
        self.tracer = PipelineTracer()
        self.tracer.log("START", f"Beginning analysis: {deal_name}", "info", {
            "file_count": len(files),
            "filenames": [f.get("filename", "unknown") for f in files],
        })
        
        # Store PA SF for synthesis stage
        self._property_appraiser_sf = property_appraiser_sf
        if property_appraiser_sf:
            self.tracer.log("BASELINE", f"Property Appraiser SF: {property_appraiser_sf:,.0f} SF (official baseline)", "info")
        else:
            self.tracer.log("BASELINE", "No Property Appraiser SF provided - will compare across documents only", "warning")
        
        # Stage 1: Ingest and prepare all files
        self.tracer.log("STAGE_1", "Ingesting files and extracting text...", "info")
        documents = await self._ingest_files(files)
        
        if not documents:
            self.tracer.log("ERROR", "No processable documents found", "error")
            return {
                "success": False,
                "deal_name": deal_name,
                "error": "No processable documents found",
                "documents_received": len(files),
                "trace_log": self.tracer.get_logs(),
            }
        
        self.tracer.log("STAGE_1", f"Ingested {len(documents)} document(s)", "success")
        
        # Stage 2: Classify each document
        self.tracer.log("STAGE_2", "Classifying documents with AI...", "info")
        classified = await self._classify_all(documents)
        for doc in classified:
            self.tracer.log("CLASSIFY", f"{doc.get('filename', 'unknown')} -> {doc.get('doc_type', 'UNKNOWN')} ({doc.get('confidence', 0)*100:.0f}%)", "info")
        self.tracer.log("STAGE_2", f"Classified {len(classified)} document(s)", "success")
        
        # Stage 3: Extract data from each document
        self.tracer.log("STAGE_3", "Extracting structured data from documents...", "info")
        extracted = await self._extract_all(classified)
        self.tracer.log("STAGE_3", f"Extracted data from {len(extracted)} document(s)", "success")
        
        # Stage 4: Synthesize cross-document analysis (uses PA SF as baseline)
        self.tracer.log("STAGE_4", "Synthesizing cross-document analysis...", "info")
        synthesis = await self._synthesize(deal_name, extracted)
        self.tracer.log("STAGE_4", "Synthesis complete", "success")
        
        # Stage 5: Build final report
        self.tracer.log("STAGE_5", "Building final report...", "info")
        report = self._build_report(deal_name, extracted, synthesis)
        
        # Add RSF finding to trace
        if report.get("rsf_recovery_sf", 0) > 0:
            self.tracer.log("RSF_ALERT", f"Discrepancy found: {report['rsf_recovery_sf']:,.0f} SF", "warning")
            if report.get("rsf_recovery_annual_value", 0) > 0:
                self.tracer.log("RSF_ALERT", f"Recovery opportunity: ${report['rsf_recovery_annual_value']:,.0f}/year", "warning")
        else:
            self.tracer.log("RSF", "No significant RSF discrepancies detected", "success")
        
        # Add score to trace
        score = report.get("score", 0)
        tier = report.get("tier", "UNKNOWN")
        level = "success" if tier == "GREEN" else "error" if tier == "RED" else "warning"
        self.tracer.log("SCORE", f"Deal Score: {score} ({tier})", level)
        
        self.tracer.log("COMPLETE", "Analysis complete!", "success")
        
        # Include trace log in response
        report["trace_log"] = self.tracer.get_logs()
        
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
        Uses multiple fallback strategies to ensure every document is readable.
        """
        documents = []
        
        for i, file in enumerate(files):
            filename = file.get("filename", f"document_{i}")
            content = file.get("content", "")
            content_type = file.get("content_type", self._guess_content_type(filename))
            
            if self.tracer:
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
            extraction_success = False
            
            # Extract text based on file type with fallback chain
            if self._is_excel(filename, content_type):
                text, success = await self._try_extract_excel(content, filename, doc)
                extraction_success = success
                
            elif self._is_pdf(filename, content_type):
                # Try multiple extraction methods for PDFs
                text, success = await self._try_extract_pdf(content, filename, doc)
                extraction_success = success
                
            elif self._is_image(filename, content_type):
                text, success = await self._try_ocr(content, filename, doc)
                extraction_success = success
                
            else:
                # Assume it's already text or try to decode
                if isinstance(content, bytes):
                    try:
                        text = content.decode('utf-8')
                        doc["extraction_method"] = "text_decode"
                        extraction_success = True
                    except:
                        text = str(content)
                        doc["extraction_method"] = "text_fallback"
                else:
                    text = str(content) if content else ""
                    doc["extraction_method"] = "text_direct"
                    extraction_success = bool(text)
            
            doc["text"] = text
            doc["char_count"] = len(text) if text else 0
            
            # Include document even if extraction failed - AI can still try to help
            if text and len(text.strip()) > 20:
                doc["source_type"] = doc.get("extraction_method", "unknown")
                documents.append(doc)
                if self.tracer:
                    self.tracer.log("INGEST", f"  -> {doc['extraction_method']}: {len(text):,} chars extracted", "success")
            elif not extraction_success:
                # Include with error so user knows what happened
                doc["source_type"] = "extraction_failed"
                doc["text"] = f"[EXTRACTION FAILED for {filename}]\n\nErrors encountered:\n" + "\n".join(doc["extraction_errors"])
                documents.append(doc)
                if self.tracer:
                    self.tracer.log("INGEST", f"  -> FAILED: {'; '.join(doc['extraction_errors'][:2])}", "error")
            else:
                if self.tracer:
                    self.tracer.log("INGEST", f"  -> Minimal content ({len(text)} chars)", "warning")
        
        return documents
    
    async def _try_extract_pdf(self, content: bytes | str, filename: str, doc: dict) -> tuple[str, bool]:
        """Try multiple methods to extract text from PDF."""
        
        # Method 1: PyPDF2 text extraction (fast, works for text-based PDFs)
        text = self._extract_pdf_text(content)
        
        # Check for extraction errors
        if text and "[PDF extraction error" in text:
            doc["extraction_errors"].append(text)
        
        # Check if we got meaningful text (>100 chars of actual content)
        if text and len(text.strip()) > 100 and "[PDF extraction error" not in text:
            doc["extraction_method"] = "pdf_text"
            if self.tracer:
                self.tracer.log("INGEST", f"  -> PDF text: {len(text):,} chars extracted", "success")
            return text, True
        
        # Sparse or no text - try OpenRouter's native PDF parsing with OCR
        sparse_chars = len(text.strip()) if text else 0
        if self.tracer:
            self.tracer.log("INGEST", f"  -> PDF has sparse text ({sparse_chars} chars). Trying AI-powered PDF parsing...", "info")
        
        # Method 2: Use OpenRouter's native PDF parsing (supports scanned documents)
        ocr_text = await self._parse_pdf_with_openrouter(content, filename)
        
        ocr_is_error = not ocr_text or "[PDF parsing error" in ocr_text or "[PDF OCR" in ocr_text
        
        if not ocr_is_error and len(ocr_text.strip()) > 50:
            doc["extraction_method"] = "pdf_ai_ocr"
            if self.tracer:
                self.tracer.log("INGEST", f"  -> AI PDF parsing: {len(ocr_text):,} chars extracted", "success")
            return ocr_text, True
        
        if ocr_is_error:
            error_detail = ocr_text[:300] if ocr_text else "no response"
            doc["extraction_errors"].append(f"AI PDF parsing failed: {error_detail}")
            if self.tracer:
                self.tracer.log("INGEST", f"  -> AI PDF parsing failed: {error_detail[:120]}", "error")
        
        # Method 3: Combine PyPDF2 text + OCR text if both got something real
        # Only use content that is NOT an error string
        real_text = text.strip() if (text and len(text.strip()) > 20 and "[PDF extraction error" not in text) else ""
        real_ocr = ocr_text.strip() if (not ocr_is_error and ocr_text and len(ocr_text.strip()) > 20) else ""
        
        combined = "\n\n".join(filter(None, [real_text, real_ocr]))
        
        if combined and len(combined.strip()) > 50:
            doc["extraction_method"] = "pdf_combined"
            if self.tracer:
                self.tracer.log("INGEST", f"  -> Combined extraction: {len(combined):,} chars", "info")
            return combined, True
        
        # Method 4 (last resort): If PyPDF2 got ANYTHING, pass it to the AI anyway.
        # The AI can often extract structure from even sparse/garbled PDF text.
        if text and len(text.strip()) > 10 and "[PDF extraction error" not in text:
            doc["extraction_method"] = "pdf_raw_fallback"
            if self.tracer:
                self.tracer.log("INGEST", f"  -> Using raw PDF text ({len(text.strip())} chars) for AI extraction", "warning")
            return text, True

        # All methods failed - pass an error description so the AI can still respond usefully
        doc["extraction_method"] = "pdf_failed"
        errors_joined = chr(10).join(doc["extraction_errors"])
        pa_sf = getattr(self, '_property_appraiser_sf', 'N/A')
        error_msg = f"""[PDF EXTRACTION FAILED: {filename}]
Errors: {errors_joined}
Property Appraiser SF baseline recorded: {pa_sf} SF
Action: Provide a text-based PDF, Excel export, or clearer scan."""
        if self.tracer:
            self.tracer.log("INGEST", f"  -> All extraction methods failed for {filename}", "error")
        return error_msg, True
    
    async def _parse_pdf_with_openrouter(self, content: bytes | str, filename: str) -> str:
        """
        Parse PDF using OpenRouter's native PDF support.
        This uses OpenRouter's file type with Mistral OCR for scanned documents.
        Works for both text-based and scanned/image-based PDFs.
        """
        try:
            import httpx
            
            if isinstance(content, bytes):
                b64_content = base64.b64encode(content).decode("utf-8")
            else:
                b64_content = content
            
            # OpenRouter PDF format: type "file" with data URL
            data_url = f"data:application/pdf;base64,{b64_content}"
            
            # Use httpx directly to include the plugins parameter
            # (OpenAI client doesn't support the plugins field)
            async with httpx.AsyncClient(timeout=120.0) as http_client:
                response = await http_client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 8000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": """Extract ALL text content from this PDF document. This is a commercial real estate document.

CRITICAL: Extract everything you can see including:
- All text, numbers, dates, names, addresses
- Table data - preserve structure with | column | separators |
- Headers, footers, page numbers
- Any handwritten notes if visible

If this is a RENT ROLL, extract for each tenant:
- Tenant Name | Suite/Unit | Square Feet | Monthly Rent | Annual Rent | Lease Start | Lease End

If this is a LEASE, extract:
- Landlord, Tenant, Property Address, Premises/Suite, SF, Lease Term, Base Rent, Escalations

Return ONLY the extracted text. No commentary or explanations."""
                                    },
                                    {
                                        "type": "file",
                                        "file": {
                                            "filename": filename,
                                            "file_data": data_url
                                        }
                                    }
                                ]
                            }
                        ],
                        # Use Mistral OCR for best scanned document support
                        "plugins": [
                            {
                                "id": "file-parser",
                                "pdf": {
                                    "engine": "mistral-ocr"
                                }
                            }
                        ]
                    }
                )
                
                if response.status_code != 200:
                    error_text = response.text
                    return f"[PDF parsing error: HTTP {response.status_code} - {error_text[:200]}]"
                
                result = response.json()
                
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                else:
                    return f"[PDF parsing error: No content in response]"
                    
        except Exception as e:
            return f"[PDF parsing error: {str(e)}]"
    
    async def _try_extract_excel(self, content: bytes | str, filename: str, doc: dict) -> tuple[str, bool]:
        """Try to extract text from Excel file."""
        text = await self._extract_excel_text(content, filename)
        
        if text and "[Excel extraction error" not in text:
            doc["extraction_method"] = "excel"
            return text, True
        
        doc["extraction_errors"].append(text if text else "Excel extraction failed")
        return "", False
    
    async def _try_ocr(self, content: bytes | str, filename: str, doc: dict) -> tuple[str, bool]:
        """Try OCR with fallback error handling."""
        text = await self._ocr_document(content, filename)
        
        if text and "[OCR error" not in text and len(text.strip()) > 20:
            doc["extraction_method"] = "ocr"
            return text, True
        
        if text and "[OCR error" in text:
            doc["extraction_errors"].append(text)
        
        return text or "", False
    
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
        """Extract text from PDF using PyPDF2 with enhanced error handling."""
        try:
            from PyPDF2 import PdfReader
            from PyPDF2.errors import PdfReadError
            
            if isinstance(content, str):
                # Might be base64 encoded
                try:
                    content = base64.b64decode(content)
                except:
                    return content  # Already text
            
            # Ensure we have bytes
            if not isinstance(content, bytes):
                return "[PDF extraction error: Invalid content type]"
            
            try:
                pdf = PdfReader(io.BytesIO(content))
            except PdfReadError as e:
                if "encrypt" in str(e).lower():
                    return "[PDF extraction error: PDF is encrypted/password-protected]"
                return f"[PDF extraction error: Cannot read PDF - {e}]"
            
            text_parts = []
            page_count = len(pdf.pages)
            
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text()
                    if text and text.strip():
                        # Clean up common OCR artifacts
                        text = text.replace('\x00', '')  # Remove null bytes
                        text_parts.append(f"--- Page {i+1} of {page_count} ---\n{text}")
                except Exception as page_error:
                    text_parts.append(f"--- Page {i+1} of {page_count} ---\n[Page extraction failed: {page_error}]")
            
            if not text_parts:
                return "[PDF extraction error: No text found in PDF - may be scanned/image-based]"
            
            return "\n\n".join(text_parts)
            
        except ImportError:
            return "[PDF extraction error: PyPDF2 not installed]"
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
        OCR images using OpenRouter's file format.
        For PDFs, use _parse_pdf_with_openrouter instead.
        """
        ext = self._get_ext(filename)
        
        # PDFs should use the dedicated PDF parsing method
        if ext == "pdf":
            return await self._parse_pdf_with_openrouter(content, filename)
        
        # For images, use OpenRouter's file format with vision
        try:
            import httpx
            
            if isinstance(content, bytes):
                b64_content = base64.b64encode(content).decode("utf-8")
            else:
                b64_content = content
            
            # Determine media type for data URL
            media_types = {
                "png": "image/png",
                "jpg": "image/jpeg",
                "jpeg": "image/jpeg",
                "tiff": "image/tiff",
                "gif": "image/gif",
                "webp": "image/webp",
            }
            media_type = media_types.get(ext, "image/png")
            
            # Check file size
            content_bytes = content if isinstance(content, bytes) else base64.b64decode(content)
            if len(content_bytes) > 10 * 1024 * 1024:  # 10MB limit
                return f"[OCR error: Image too large ({len(content_bytes) / 1024 / 1024:.1f}MB). Please provide a smaller image.]"
            
            data_url = f"data:{media_type};base64,{b64_content}"
            
            # Use OpenRouter with file type for images
            async with httpx.AsyncClient(timeout=120.0) as http_client:
                response = await http_client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 8000,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {
                                        "type": "text",
                                        "text": """Extract ALL text from this image. This is a commercial real estate document.

CRITICAL: Extract everything visible including:
- All text, numbers, dates, names, addresses
- Table data with | column | separators |
- Headers, labels, annotations

If this is a RENT ROLL, extract: Tenant Name | Suite | SF | Rent | Lease Dates
If this is a LEASE page, extract: All visible terms and conditions

Return ONLY the extracted text."""
                                    },
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": data_url
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                )
                
                if response.status_code != 200:
                    return f"[OCR error: HTTP {response.status_code} - {response.text[:200]}]"
                
                result = response.json()
                if "choices" in result and len(result["choices"]) > 0:
                    return result["choices"][0]["message"]["content"]
                return "[OCR error: No content in response]"
                
        except Exception as e:
            return f"[OCR error: {str(e)}]"
    
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
        
        # AI returns "document_type" but we use "doc_type" internally
        # Handle both field names defensively
        doc_type = (
            result.get("doc_type")
            or result.get("document_type")
            or result.get("type")
            or "UNKNOWN"
        )
        
        # Normalize to our known types
        doc_type = doc_type.upper().strip()
        known_types = {
            "LEASE", "LEASE_ABSTRACT", "RENT_ROLL", "RENT_ROLL_XLSX",
            "BOMA", "FINANCIAL_MODEL", "CAM_RECONCILIATION",
            "MANAGEMENT_REPORT", "COUNTY_PA"
        }
        if doc_type not in known_types:
            # Try fuzzy match - e.g. "RENT ROLL" -> "RENT_ROLL"
            doc_type_normalized = doc_type.replace(" ", "_")
            doc_type = doc_type_normalized if doc_type_normalized in known_types else "UNKNOWN"
        
        return {
            "doc_type": doc_type,
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
        
        # Get Property Appraiser SF baseline (the TRUTH)
        pa_sf = getattr(self, '_property_appraiser_sf', None)
        
        # Build summary for synthesis
        summary = {
            "deal_name": deal_name,
            "property_appraiser_sf": pa_sf,  # Official baseline from county records
            "document_types_present": list(by_type.keys()),
            "document_count": len(documents),
            "documents_by_type": {k: len(v) for k, v in by_type.items()},
            "extractions": by_type,
        }
        
        # Build PA context for the prompt
        pa_context = ""
        if pa_sf:
            pa_context = f"""
*** CRITICAL: PROPERTY APPRAISER BASELINE ***
The official Property Appraiser SF is {pa_sf:,.0f} SF. This is the AUTHORITATIVE TRUTH.
- This is the actual building size according to county records
- Compare ALL rent roll SF and lease SF against this official number
- If rent roll total < PA SF, tenants may be underpaying
- Recovery = (PA SF - Rent Roll Total SF) * average rent PSF
"""
        else:
            pa_context = """
NOTE: No Property Appraiser SF was provided as baseline. 
Compare SF across available documents only.
"""
        
        prompt = f"""Analyze this CRE deal package and produce a comprehensive JSON report.

CRITICAL FOCUS: Identify RSF (rentable square footage) discrepancies between sources.
{pa_context}

Deal Package:
{json.dumps(summary, indent=2, default=str)}

YOU MUST return ONLY valid JSON with EXACTLY these top-level keys (no others, no renaming):

{{
  "rsf_reconciliation": {{
    "property_appraiser_sf": {pa_sf if pa_sf else 0},
    "rent_roll_total_sf": <number>,
    "discrepancy_sf": <number: PA_sf minus rent_roll_sf>,
    "discrepancy_pct": <number>,
    "alert_triggered": <true if discrepancy > 2%>
  }},
  "rsf_recovery_opportunity": {{
    "recoverable_sf": <number>,
    "average_rent_psf": <number>,
    "estimated_annual_recovery": <number: recoverable_sf * avg_rent_psf>
  }},
  "tenant_analysis": [
    {{
      "tenant": "<name>",
      "suite": "<suite/unit>",
      "rsf": <number>,
      "annual_rent": <number>,
      "monthly_rent": <number>,
      "lease_start": "<YYYY-MM-DD or empty>",
      "lease_end": "<YYYY-MM-DD or empty>",
      "months_remaining": <number or null>,
      "risk_level": "<LOW|MEDIUM|HIGH>"
    }}
  ],
  "red_flags": [
    {{
      "severity": "<CRITICAL|HIGH|MODERATE|LOW>",
      "category": "<category>",
      "flag": "<short identifier>",
      "description": "<what the problem is>",
      "impact": "<financial or operational impact>",
      "resolution": "<recommended action>"
    }}
  ],
  "deal_score": {{
    "overall_score": <0-100>,
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

RULES:
- Do NOT add any keys not listed above
- Do NOT rename keys (e.g. do not use "rent_verification" instead of "tenant_analysis")
- tenant_analysis MUST be an array of tenant objects as shown above
- All numbers must be plain numbers, not strings
- Return ONLY the JSON object, no markdown fences"""

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
        # Extract key metrics — new prompt uses lowercase, keep UPPERCASE fallback
        rsf_recon  = synthesis.get("rsf_reconciliation")  or synthesis.get("RSF_RECONCILIATION")  or {}
        recovery   = synthesis.get("rsf_recovery_opportunity") or synthesis.get("RSF_RECOVERY_OPPORTUNITY") or {}
        red_flags  = synthesis.get("red_flags")  or synthesis.get("RED_FLAGS")  or []
        score_data = synthesis.get("deal_score") or synthesis.get("DEAL_SCORE") or {}
        
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
        
        # Extract score - AI returns 'overall_score', 'score', or 'overall'
        score_value = (
            score_data.get("overall_score")
            or score_data.get("score")
            or score_data.get("overall")
            or score_data.get("total_score")
            or 0
        )
        if isinstance(score_value, str):
            try:
                score_value = float(score_value.replace(',', ''))
            except:
                score_value = 0
        score_value = float(score_value)
        
        # Use AI-provided tier if available, otherwise derive it
        ai_tier = score_data.get("tier", "")
        tier_value = self._score_to_tier(score_value) if not ai_tier else self._normalize_tier(ai_tier)
        
        # Extract RSF recovery - AI returns 'recoverable_sf' and 'estimated_annual_recovery'
        rsf_recovery_sf = (
            recovery.get("recoverable_sf")
            or recovery.get("sf")
            or recovery.get("discrepancy_sf")
            or recovery.get("opportunity_sf")
            or 0
        ) or 0
        rsf_recovery_value = (
            recovery.get("estimated_annual_recovery")
            or recovery.get("annual_value")
            or recovery.get("potential_recovery")
            or recovery.get("estimated_recovery")
            or 0
        ) or 0
        
        def _safe_float(v) -> float:
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(',', '').replace('$', '').strip())
                except:
                    return 0.0
            return 0.0
        
        rsf_recovery_sf = _safe_float(rsf_recovery_sf)
        rsf_recovery_value = _safe_float(rsf_recovery_value)
        
        # Get Property Appraiser SF baseline
        pa_sf = getattr(self, '_property_appraiser_sf', None)
        
        return {
            "success": True,
            "deal_name": deal_name,
            "analyzed_at": datetime.utcnow().isoformat(),
            
            # TOP-LEVEL FIELDS (what frontend expects)
            "documents_processed": len(documents),
            "property_appraiser_sf": pa_sf,
            "score": score_value,
            "tier": tier_value,
            "rsf_recovery_sf": rsf_recovery_sf,
            "rsf_recovery_annual_value": rsf_recovery_value,
            "red_flags": red_flags,
            
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
                "reconciliation": {
                    **rsf_recon,
                    "property_appraiser_sf": pa_sf,
                },
                "recovery_opportunity": recovery,
                "discrepancy_found": bool(rsf_recovery_sf > 0),
            },
            
            # Risk assessment
            "risk": {
                "score": score_value,
                "tier": tier_value,
                "sub_scores": score_data.get("sub_scores", {}),
                "red_flags": red_flags,
                "red_flag_count": {
                    "critical": len([f for f in red_flags if f.get("severity") == "CRITICAL"]),
                    "high": len([f for f in red_flags if f.get("severity") == "HIGH"]),
                    "moderate": len([f for f in red_flags if f.get("severity") == "MODERATE"]),
                    "low": len([f for f in red_flags if f.get("severity") == "LOW"]),
                },
            },
            
            # Tenants - try all key variants the AI might return
            "tenants": self._extract_tenants(synthesis),
            
            # Financial - try all key variants
            "financial": (
                synthesis.get("FINANCIAL_SUMMARY")
                or synthesis.get("financial_summary")
                or synthesis.get("financial_analysis")
                or {}
            ),
            
            # Next steps - ensure it's always a list, try all key variants
            "what_to_get_next": self._normalize_to_list(
                synthesis.get("WHAT_TO_GET_NEXT")
                or synthesis.get("what_to_get_next")
                or synthesis.get("missing_documents")
                or []
            ),
            
            # Full synthesis for reference
            "_raw_synthesis": synthesis,
        }
    
    def _extract_tenants(self, synthesis: dict) -> list:
        """
        Extract tenants from synthesis, trying every key the AI might use.
        The AI sometimes puts tenants in TENANT_ANALYSIS, rent_verification.tenants,
        lease_audit.tenants, or similar nested locations.
        """
        # Primary key - what the new prompt enforces
        for key in ["tenant_analysis", "TENANT_ANALYSIS", "tenants", "TENANTS", "tenant_roster"]:
            val = synthesis.get(key)
            if val:
                result = self._normalize_to_list(val)
                if result:
                    return result

        # Fallback: rent_verification.tenant_shares (old AI schema)
        rv = synthesis.get("rent_verification") or synthesis.get("RENT_VERIFICATION") or {}
        if isinstance(rv, dict):
            shares = rv.get("tenant_shares") or rv.get("tenants") or rv.get("tenant_list") or []
            if shares:
                return self._normalize_to_list(shares)

        # Fallback: lease_audit
        la = synthesis.get("lease_audit") or synthesis.get("LEASE_AUDIT") or {}
        if isinstance(la, dict):
            for key in ["tenants", "abstracts", "leases"]:
                val = la.get(key)
                if val:
                    result = self._normalize_to_list(val)
                    if result:
                        return result

        return []

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

    def _normalize_tier(self, tier_str: str) -> str:
        """Normalize AI-returned tier strings to GREEN/YELLOW/ORANGE/RED."""
        t = str(tier_str).upper().strip()
        mapping = {
            "GREEN": "GREEN", "PASS": "GREEN", "LOW RISK": "GREEN",
            "YELLOW": "YELLOW", "CAUTION": "YELLOW", "UNDER REVIEW": "YELLOW", "MODERATE RISK": "YELLOW",
            "ORANGE": "ORANGE", "HIGH RISK": "ORANGE", "ELEVATED": "ORANGE",
            "RED": "RED", "CRITICAL": "RED", "FAIL": "RED", "VERY HIGH RISK": "RED",
        }
        return mapping.get(t, self._score_to_tier(0))
    
    def _normalize_to_list(self, value) -> list:
        """Ensure a value is always a list, filtering out None/null items."""
        if value is None:
            return []
        if isinstance(value, list):
            # Filter out None/null items - these cause frontend crashes
            return [item for item in value if item is not None]
        if isinstance(value, dict):
            # If it's a dict with items, try to extract them
            if "tenants" in value:
                return self._normalize_to_list(value["tenants"])
            if "items" in value:
                return self._normalize_to_list(value["items"])
            if "list" in value:
                return self._normalize_to_list(value["list"])
            # Return as single-item list if dict has content
            return [value] if value else []
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
