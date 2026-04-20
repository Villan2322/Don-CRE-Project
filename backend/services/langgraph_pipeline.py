"""
CRE Document Intelligence Pipeline - LangGraph Implementation

This implements the same pipeline using LangGraph for:
1. Visual graph representation
2. Full tracing via LangSmith
3. Step-by-step observability
4. Streaming updates

Stages:
1. INGEST - File type detection, text extraction, OCR if needed
2. CLASSIFY - AI classifies each doc into 9 CRE document types
3. EXTRACT - Config-driven extraction of structured data per doc type
4. SYNTHESIZE - Cross-document analysis, RSF reconciliation
5. REPORT - Build final output for frontend
"""

import os
import json
import base64
import io
import asyncio
from datetime import datetime
from typing import TypedDict, Annotated, Sequence, Any
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langsmith import traceable
from openai import AsyncOpenAI

from config.extraction_prompts import (
    EXTRACTION_PROMPTS,
    CLASSIFICATION_PROMPT,
    SYNTHESIS_PROMPT,
    DOC_TYPES,
)


# =============================================================================
# STATE DEFINITION
# =============================================================================

class PipelineState(TypedDict):
    """State passed through the pipeline graph."""
    # Input
    deal_name: str
    raw_files: list[dict]
    
    # After ingestion
    documents: list[dict]
    
    # After classification
    classified_documents: list[dict]
    
    # After extraction
    extracted_documents: list[dict]
    
    # After synthesis
    synthesis: dict
    
    # Final output
    report: dict
    
    # Tracing
    trace_log: list[dict]
    current_stage: str
    errors: list[str]


# =============================================================================
# TRACER - Logs each step for frontend display
# =============================================================================

@dataclass
class PipelineTracer:
    """Tracks pipeline execution for observability."""
    logs: list[dict] = field(default_factory=list)
    
    def log(self, stage: str, message: str, level: str = "info", data: dict = None):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "stage": stage,
            "message": message,
            "level": level,
            "data": data or {},
        }
        self.logs.append(entry)
        print(f"[{stage}] {message}")  # Also print for server logs
        return entry
    
    def to_list(self) -> list[dict]:
        return self.logs


# =============================================================================
# LANGGRAPH PIPELINE
# =============================================================================

class CRELangGraphPipeline:
    """
    LangGraph-based CRE Document Intelligence Pipeline.
    
    Provides full tracing and step-by-step observability.
    """
    
    def __init__(self, api_key: str = None):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key or os.environ.get("OPENROUTER_API_KEY", ""),
        )
        self.model = "anthropic/claude-sonnet-4"
        self.tracer = PipelineTracer()
        self.graph = self._build_graph()
    
    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine."""
        
        # Define the graph
        workflow = StateGraph(PipelineState)
        
        # Add nodes (stages)
        workflow.add_node("ingest", self._node_ingest)
        workflow.add_node("classify", self._node_classify)
        workflow.add_node("extract", self._node_extract)
        workflow.add_node("synthesize", self._node_synthesize)
        workflow.add_node("report", self._node_report)
        
        # Define edges (flow)
        workflow.set_entry_point("ingest")
        workflow.add_edge("ingest", "classify")
        workflow.add_edge("classify", "extract")
        workflow.add_edge("extract", "synthesize")
        workflow.add_edge("synthesize", "report")
        workflow.add_edge("report", END)
        
        return workflow.compile()
    
    # =========================================================================
    # MAIN ENTRY POINT
    # =========================================================================
    
    @traceable(name="CRE Pipeline - Full Analysis")
    async def analyze(self, files: list[dict], deal_name: str = None) -> dict:
        """
        Run the full pipeline with tracing.
        
        Args:
            files: List of {filename, content, content_type}
            deal_name: Optional name for this analysis
            
        Returns:
            Complete analysis with trace log
        """
        self.tracer = PipelineTracer()  # Fresh tracer for each run
        
        if not deal_name:
            deal_name = f"Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        self.tracer.log("START", f"Beginning analysis: {deal_name}", "info", {
            "file_count": len(files),
            "filenames": [f.get("filename", "unknown") for f in files],
        })
        
        # Initial state
        initial_state: PipelineState = {
            "deal_name": deal_name,
            "raw_files": files,
            "documents": [],
            "classified_documents": [],
            "extracted_documents": [],
            "synthesis": {},
            "report": {},
            "trace_log": [],
            "current_stage": "START",
            "errors": [],
        }
        
        try:
            # Run the graph
            final_state = await self.graph.ainvoke(initial_state)
            
            # Add trace log to report
            report = final_state.get("report", {})
            report["trace_log"] = self.tracer.to_list()
            report["success"] = True
            
            self.tracer.log("COMPLETE", f"Analysis complete. Score: {report.get('score', 'N/A')}", "success")
            
            return report
            
        except Exception as e:
            self.tracer.log("ERROR", f"Pipeline failed: {str(e)}", "error")
            return {
                "success": False,
                "error": str(e),
                "trace_log": self.tracer.to_list(),
                "deal_name": deal_name,
            }
    
    # =========================================================================
    # NODE: INGEST - File type detection and text extraction
    # =========================================================================
    
    @traceable(name="Stage 1: Ingest Files")
    async def _node_ingest(self, state: PipelineState) -> PipelineState:
        """Ingest all files - detect type, extract text, OCR if needed."""
        
        self.tracer.log("INGEST", "Starting file ingestion", "info")
        documents = []
        
        for i, file in enumerate(state["raw_files"]):
            filename = file.get("filename", f"doc_{i}")
            content = file.get("content", "")
            content_type = file.get("content_type", "")
            
            self.tracer.log("INGEST", f"Processing: {filename}", "info", {
                "content_type": content_type,
                "size_bytes": len(content) if isinstance(content, (str, bytes)) else 0,
            })
            
            doc = {
                "id": f"doc_{i}",
                "filename": filename,
                "content_type": content_type,
            }
            
            # Extract text based on file type
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            
            if ext in ["xlsx", "xls", "csv"]:
                self.tracer.log("INGEST", f"  -> Excel file, extracting sheets", "info")
                doc["text"] = await self._extract_excel(content)
                doc["source_type"] = "excel"
                
            elif ext == "pdf" or content_type == "application/pdf":
                text = self._extract_pdf(content)
                if len(text.strip()) < 100:
                    self.tracer.log("INGEST", f"  -> Scanned PDF, running OCR", "warning")
                    doc["text"] = await self._ocr(content, filename)
                    doc["source_type"] = "pdf_ocr"
                else:
                    self.tracer.log("INGEST", f"  -> Text PDF, extracted {len(text)} chars", "info")
                    doc["text"] = text
                    doc["source_type"] = "pdf_text"
                    
            elif ext in ["png", "jpg", "jpeg", "tiff", "tif"]:
                self.tracer.log("INGEST", f"  -> Image file, running OCR", "info")
                doc["text"] = await self._ocr(content, filename)
                doc["source_type"] = "image_ocr"
                
            else:
                doc["text"] = content if isinstance(content, str) else str(content)
                doc["source_type"] = "text"
            
            if doc.get("text") and len(doc["text"].strip()) > 50:
                doc["char_count"] = len(doc["text"])
                documents.append(doc)
                self.tracer.log("INGEST", f"  -> Ingested successfully ({doc['char_count']} chars)", "success")
            else:
                self.tracer.log("INGEST", f"  -> Skipped (insufficient text)", "warning")
        
        self.tracer.log("INGEST", f"Ingestion complete: {len(documents)} documents", "success")
        
        state["documents"] = documents
        state["current_stage"] = "INGEST"
        return state
    
    # =========================================================================
    # NODE: CLASSIFY - AI classification of document types
    # =========================================================================
    
    @traceable(name="Stage 2: Classify Documents")
    async def _node_classify(self, state: PipelineState) -> PipelineState:
        """Classify all documents using AI."""
        
        self.tracer.log("CLASSIFY", f"Classifying {len(state['documents'])} documents", "info")
        
        # Classify in parallel
        tasks = [self._classify_one(doc) for doc in state["documents"]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for doc, result in zip(state["documents"], results):
            if isinstance(result, Exception):
                doc["doc_type"] = "UNKNOWN"
                doc["confidence"] = 0
                self.tracer.log("CLASSIFY", f"  {doc['filename']}: ERROR - {result}", "error")
            else:
                doc.update(result)
                self.tracer.log("CLASSIFY", 
                    f"  {doc['filename']}: {doc['doc_type']} ({doc.get('confidence', 0)*100:.0f}% confidence)", 
                    "success",
                    {"doc_type": doc["doc_type"], "confidence": doc.get("confidence")}
                )
        
        state["classified_documents"] = state["documents"]
        state["current_stage"] = "CLASSIFY"
        return state
    
    @traceable(name="Classify Single Document")
    async def _classify_one(self, doc: dict) -> dict:
        """Classify a single document."""
        text = doc.get("text", "")
        sample = text[:2000]
        if len(text) > 4000:
            sample += "\n\n[...]\n\n" + text[-2000:]
        
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"Filename: {doc.get('filename')}\n\nText:\n{sample}"}
            ],
        )
        
        result = self._parse_json(response.choices[0].message.content)
        return {
            "doc_type": result.get("doc_type", "UNKNOWN"),
            "confidence": result.get("confidence", 0.5),
            "reasoning": result.get("reasoning", ""),
        }
    
    # =========================================================================
    # NODE: EXTRACT - Pull structured data based on doc type
    # =========================================================================
    
    @traceable(name="Stage 3: Extract Data")
    async def _node_extract(self, state: PipelineState) -> PipelineState:
        """Extract structured data from all documents."""
        
        self.tracer.log("EXTRACT", f"Extracting data from {len(state['classified_documents'])} documents", "info")
        
        # Extract in parallel
        tasks = [self._extract_one(doc) for doc in state["classified_documents"]]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for doc, result in zip(state["classified_documents"], results):
            if isinstance(result, Exception):
                doc["extraction"] = {"error": str(result)}
                self.tracer.log("EXTRACT", f"  {doc['filename']}: ERROR - {result}", "error")
            else:
                doc["extraction"] = result
                field_count = len([k for k, v in result.items() if v is not None and k != "_note"])
                self.tracer.log("EXTRACT", 
                    f"  {doc['filename']}: Extracted {field_count} fields", 
                    "success",
                    {"fields_extracted": field_count}
                )
                
                # Enrich lease documents
                if doc.get("doc_type") in ["LEASE", "LEASE_ABSTRACT"]:
                    self._enrich_lease(doc)
        
        state["extracted_documents"] = state["classified_documents"]
        state["current_stage"] = "EXTRACT"
        return state
    
    @traceable(name="Extract Single Document")
    async def _extract_one(self, doc: dict) -> dict:
        """Extract data from one document using config-driven prompts."""
        doc_type = doc.get("doc_type", "UNKNOWN")
        config = EXTRACTION_PROMPTS.get(doc_type)
        
        if not config:
            return {"_note": f"No extraction config for {doc_type}"}
        
        text = doc.get("text", "")
        if len(text) > 40000:
            text = text[:20000] + "\n\n[...truncated...]\n\n" + text[-20000:]
        
        prompt = f"""Extract the following fields from this {doc_type} document.

Fields: {', '.join(config.get('fields', []))}

Document:
{text}

Return JSON with each field. Use null if not found."""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": config.get("system", "You are a CRE analyst.")},
                {"role": "user", "content": prompt},
            ],
        )
        
        return self._parse_json(response.choices[0].message.content)
    
    def _enrich_lease(self, doc: dict):
        """Calculate lease risk metrics."""
        ext = doc.get("extraction", {})
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
        
        doc["enriched"] = {"months_remaining": months_remaining, "risk_level": risk_level}
    
    # =========================================================================
    # NODE: SYNTHESIZE - Cross-document analysis
    # =========================================================================
    
    @traceable(name="Stage 4: Synthesize Analysis")
    async def _node_synthesize(self, state: PipelineState) -> PipelineState:
        """Cross-reference all documents and produce analysis."""
        
        self.tracer.log("SYNTHESIZE", "Synthesizing cross-document analysis", "info")
        
        # Group by type
        by_type = {}
        for doc in state["extracted_documents"]:
            dtype = doc.get("doc_type", "UNKNOWN")
            if dtype not in by_type:
                by_type[dtype] = []
            by_type[dtype].append({
                "filename": doc.get("filename"),
                "extraction": doc.get("extraction", {}),
                "enriched": doc.get("enriched", {}),
            })
        
        self.tracer.log("SYNTHESIZE", f"  Document types: {list(by_type.keys())}", "info")
        
        summary = {
            "deal_name": state["deal_name"],
            "document_types": list(by_type.keys()),
            "document_count": len(state["extracted_documents"]),
            "extractions": by_type,
        }
        
        prompt = f"""Analyze this CRE deal package. Focus on RSF discrepancies.

Deal Package:
{json.dumps(summary, indent=2, default=str)}

Return JSON with:
1. RSF_RECONCILIATION - Compare SF across sources, calculate discrepancy
2. RSF_RECOVERY_OPPORTUNITY - Potential annual revenue from SF corrections
3. TENANT_ANALYSIS - List tenants with SF from each source
4. RED_FLAGS - Issues by severity (CRITICAL, HIGH, MODERATE, LOW)
5. DEAL_SCORE - Score 0-100 with sub-scores
6. WHAT_TO_GET_NEXT - Missing documents to request
7. FINANCIAL_SUMMARY - NOI, vacancy, WALT if available"""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": SYNTHESIS_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        
        synthesis = self._parse_json(response.choices[0].message.content)
        
        # Log key findings
        rsf = synthesis.get("RSF_RECONCILIATION", synthesis.get("rsf_reconciliation", {}))
        if rsf.get("discrepancy_sf"):
            self.tracer.log("SYNTHESIZE", 
                f"  RSF DISCREPANCY FOUND: {rsf.get('discrepancy_sf')} SF", 
                "warning",
                rsf
            )
        
        score = synthesis.get("DEAL_SCORE", synthesis.get("deal_score", {}))
        if isinstance(score, dict):
            self.tracer.log("SYNTHESIZE", f"  Deal Score: {score.get('overall', score.get('score', 'N/A'))}", "info")
        
        state["synthesis"] = synthesis
        state["current_stage"] = "SYNTHESIZE"
        return state
    
    # =========================================================================
    # NODE: REPORT - Build final output
    # =========================================================================
    
    @traceable(name="Stage 5: Build Report")
    async def _node_report(self, state: PipelineState) -> PipelineState:
        """Build the final report."""
        
        self.tracer.log("REPORT", "Building final report", "info")
        
        synthesis = state["synthesis"]
        
        # Extract and normalize data
        rsf = synthesis.get("RSF_RECONCILIATION", synthesis.get("rsf_reconciliation", {}))
        recovery = synthesis.get("RSF_RECOVERY_OPPORTUNITY", synthesis.get("rsf_recovery_opportunity", {}))
        red_flags = self._normalize_list(synthesis.get("RED_FLAGS", synthesis.get("red_flags", [])))
        score_data = synthesis.get("DEAL_SCORE", synthesis.get("deal_score", {}))
        tenants = self._normalize_list(synthesis.get("TENANT_ANALYSIS", synthesis.get("tenant_analysis", [])))
        next_docs = self._normalize_list(synthesis.get("WHAT_TO_GET_NEXT", synthesis.get("what_to_get_next", [])))
        financial = synthesis.get("FINANCIAL_SUMMARY", synthesis.get("financial_summary", {}))
        
        # Build report
        report = {
            "success": True,
            "deal_name": state["deal_name"],
            "documents_processed": len(state["extracted_documents"]),
            "document_classifications": [
                {"filename": d["filename"], "doc_type": d.get("doc_type"), "confidence": d.get("confidence")}
                for d in state["extracted_documents"]
            ],
            
            # RSF Analysis (Don's focus)
            "rsf_reconciliation": rsf,
            "rsf_recovery_sf": recovery.get("recoverable_sf", recovery.get("discrepancy_sf", 0)),
            "rsf_recovery_annual_value": recovery.get("annual_value", recovery.get("potential_recovery", 0)),
            
            # Scoring
            "score": score_data.get("overall", score_data.get("score", 0)) if isinstance(score_data, dict) else score_data,
            "tier": self._score_to_tier(score_data.get("overall", score_data.get("score", 50)) if isinstance(score_data, dict) else 50),
            "sub_scores": score_data.get("sub_scores", {}) if isinstance(score_data, dict) else {},
            
            # Analysis
            "tenants": tenants,
            "red_flags": red_flags,
            "what_to_get_next": next_docs,
            
            # Financial
            "noi": financial.get("noi"),
            "vacancy_pct": financial.get("vacancy_pct", financial.get("vacancy")),
            "walt_months": financial.get("walt_months", financial.get("walt")),
            
            # Metadata
            "analysis_timestamp": datetime.utcnow().isoformat(),
        }
        
        self.tracer.log("REPORT", f"Report complete: Score {report['score']}, {len(red_flags)} flags", "success")
        
        state["report"] = report
        state["current_stage"] = "REPORT"
        return state
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _parse_json(self, text: str) -> dict:
        """Extract JSON from AI response."""
        text = text.strip()
        
        # Try direct parse
        try:
            return json.loads(text)
        except:
            pass
        
        # Try to find JSON in markdown code blocks
        import re
        patterns = [
            r'```json\s*([\s\S]*?)\s*```',
            r'```\s*([\s\S]*?)\s*```',
            r'\{[\s\S]*\}',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group(1) if '```' in pattern else match.group(0))
                except:
                    continue
        
        return {"_raw": text, "_parse_error": "Could not extract JSON"}
    
    def _normalize_list(self, value) -> list:
        """Ensure value is a list."""
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return list(value.values()) if value else []
        return [value]
    
    def _score_to_tier(self, score: float) -> str:
        if score >= 85:
            return "GREEN"
        elif score >= 70:
            return "YELLOW"
        elif score >= 50:
            return "ORANGE"
        return "RED"
    
    def _extract_pdf(self, content) -> str:
        """Extract text from PDF."""
        try:
            from PyPDF2 import PdfReader
            if isinstance(content, str):
                try:
                    content = base64.b64decode(content)
                except:
                    return content
            pdf = PdfReader(io.BytesIO(content))
            return "\n\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception as e:
            return f"[PDF error: {e}]"
    
    async def _extract_excel(self, content) -> str:
        """Extract text from Excel."""
        try:
            import pandas as pd
            if isinstance(content, str):
                content = base64.b64decode(content)
            excel = pd.ExcelFile(io.BytesIO(content))
            parts = []
            for sheet in excel.sheet_names:
                df = pd.read_excel(excel, sheet_name=sheet)
                parts.append(f"=== {sheet} ===\n{df.to_string()}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"[Excel error: {e}]"
    
    async def _ocr(self, content, filename: str) -> str:
        """OCR using Claude vision."""
        try:
            if isinstance(content, bytes):
                b64 = base64.b64encode(content).decode()
            else:
                b64 = content
            
            ext = filename.rsplit(".", 1)[-1].lower()
            media = {"pdf": "application/pdf", "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(ext, "image/png")
            
            response = await self.client.chat.completions.create(
                model=self.model,
                max_tokens=8000,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": media, "data": b64}},
                        {"type": "text", "text": "Extract ALL text from this document. Preserve structure."}
                    ]
                }],
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"[OCR error: {e}]"


# =============================================================================
# FACTORY - Get the right pipeline
# =============================================================================

def get_pipeline(use_langgraph: bool = True) -> CRELangGraphPipeline:
    """Get a pipeline instance."""
    return CRELangGraphPipeline()
