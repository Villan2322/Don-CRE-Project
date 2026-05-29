import fastapi
import fastapi.middleware.cors
from fastapi import UploadFile, File, Form, HTTPException
from typing import Optional
import uuid

from models.schemas import (
    UploadResponse,
    AnalysisRequest,
    AnalysisResponse,
    ProcessingStatus,
    ProcessedDocument,
    AnalysisResult,
)
from services.document_processor import processor
from graph import graph

app = fastapi.FastAPI(
    title="CRE Document Intelligence API",
    description="AI-powered document analysis for commercial real estate due diligence",
    version="1.0.0"
)

app.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "cre-document-intelligence"}


@app.get("/diagnostics")
async def diagnostics() -> dict:
    """
    Backend self-check for monitoring. Reports which credentials and
    capabilities are available WITHOUT leaking any secret values, so you can
    tell at a glance why analysis might be failing.
    """
    import os

    anthropic_key = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    gateway_token = bool(os.environ.get("ANTHROPIC_AUTH_TOKEN", "").strip())

    # Optional libraries (text extraction). OCR no longer needs system binaries.
    def _has(mod: str) -> bool:
        try:
            __import__(mod)
            return True
        except Exception:
            return False

    return {
        "status": "ok",
        "service": "cre-document-intelligence",
        "credentials": {
            "anthropic_api_key_set": anthropic_key,
            "anthropic_gateway_token_set": gateway_token,
            "llm_reachable": anthropic_key or gateway_token,
        },
        "capabilities": {
            "pdf_text_extraction": _has("PyPDF2"),
            "excel_extraction": _has("openpyxl"),
            "vision_ocr": "claude_native",  # no tesseract/poppler needed
        },
        "model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
        "langsmith_tracing": os.environ.get("LANGSMITH_TRACING") == "true"
        and bool(os.environ.get("LANGSMITH_API_KEY", "").strip()),
    }


@app.post("/documents/upload", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)) -> UploadResponse:
    """
    Upload a document for processing.
    
    Supported formats:
    - PDF (leases, reports)
    - Excel (rent rolls, financial data)
    - CSV (tabular data)
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    
    content_type = file.content_type or "application/octet-stream"
    
    # Read file content
    file_content = await file.read()
    
    # Process document
    doc = await processor.process_document(
        filename=file.filename,
        file_content=file_content,
        content_type=content_type
    )
    
    return UploadResponse(
        message=f"Document '{file.filename}' uploaded and classified as {doc.document_type.value}",
        document_id=doc.id,
        status=doc.status,
        document_type=doc.document_type.value
    )


@app.get("/documents", response_model=list[ProcessedDocument])
async def list_documents() -> list[ProcessedDocument]:
    """List all uploaded documents."""
    return list(processor.documents.values())


@app.get("/documents/{document_id}", response_model=ProcessedDocument)
async def get_document(document_id: str) -> ProcessedDocument:
    """Get details of a specific document."""
    if document_id not in processor.documents:
        raise HTTPException(status_code=404, detail="Document not found")
    return processor.documents[document_id]


@app.post("/analyze")
async def analyze_deal(
    deal_name: str = Form(...),
    files: list[UploadFile] = File(...),
) -> dict:
    """
    Run full AI analysis pipeline on uploaded documents using LangGraph.
    
    This orchestrates all AI agents:
    1. Document Ingestion & OCR
    2. Document Classification
    3. Universal Extraction
    4. Synthesis
    5. Arithmetic Verification
    6. RSF Reconciliation
    7. Red Flag Detection
    8. Risk Scoring
    """
    deal_id = str(uuid.uuid4())
    raw_files = {}
    content_types = {}
    for f in files:
        if not f.filename:
            continue
        raw_files[f.filename] = await f.read()
        content_types[f.filename] = f.content_type or "application/octet-stream"

    if not raw_files:
        raise HTTPException(status_code=400, detail="No files provided")

    initial_state = {
        "deal_id": deal_id, "deal_name": deal_name,
        "raw_files": raw_files, "file_content_types": content_types,
        "raw_documents": [], "ingest_errors": [],
        "classified_documents": [], "classification_errors": [],
        "extractions": [], "extraction_errors": [],
        "synthesis": {}, "rsf_recovery": {}, "score_summary": {},
        "synthesis_error": None, "arithmetic_verification": {},
        "rent_roll_analysis": {}, "rsf_reconciliation": {},
        "red_flags_result": {}, "deal_score_result": {},
        "completeness_result": {}, "pipeline_stage": "pending",
        "pipeline_errors": [], "completed_at": None,
    }

    print(f"[ANALYZE] deal={deal_name} id={deal_id} files={list(raw_files.keys())}")
    result = await graph.ainvoke(initial_state)
    processor.deals[deal_id] = {"result": result, "raw_data": result}

    # Collect EVERY error/warning from every stage. Previously only
    # pipeline_errors was returned, so failures during ingest/OCR,
    # classification, or extraction were silently swallowed and the deal just
    # showed up as 0/100 with no explanation.
    ingest_errors = result.get("ingest_errors", []) or []
    classification_errors = result.get("classification_errors", []) or []
    extraction_errors = result.get("extraction_errors", []) or []
    pipeline_errors = result.get("pipeline_errors", []) or []
    synthesis_error = result.get("synthesis_error")

    all_errors = (
        [f"ingest: {e}" for e in ingest_errors]
        + [f"classify: {e}" for e in classification_errors]
        + [f"extract: {e}" for e in extraction_errors]
        + [f"pipeline: {e}" for e in pipeline_errors]
        + ([f"synthesis: {synthesis_error}"] if synthesis_error else [])
    )

    extractions = result.get("extractions", [])
    raw_docs = result.get("raw_documents", [])
    classified = result.get("classified_documents", [])

    # Per-document trace so the UI / logs can show exactly what happened to each
    # uploaded file (was it parsed? did OCR run? what type? did it extract?).
    doc_trace = []
    extraction_by_id = {e.get("doc_id"): e for e in extractions}
    for cd in classified:
        ext = extraction_by_id.get(cd.get("doc_id"), {})
        doc_trace.append({
            "filename": cd.get("filename"),
            "doc_type": cd.get("doc_type"),
            "classification_confidence": cd.get("classification_confidence"),
            "ocr_performed": cd.get("ocr_performed"),
            "parse_method": cd.get("parse_method"),
            "text_chars": len(cd.get("extracted_text", "") or ""),
            "extracted": bool(ext.get("extraction")),
            "extraction_error": ext.get("parse_error"),
        })

    print(
        f"[ANALYZE] done stage={result.get('pipeline_stage')} "
        f"raw_docs={len(raw_docs)} classified={len(classified)} "
        f"extractions={len(extractions)} errors={len(all_errors)}"
    )
    if all_errors:
        for e in all_errors:
            print(f"[ANALYZE][error] {e}")

    # Return FULL result directly since serverless can't persist state between calls
    return {
        "deal_id": deal_id,
        "deal_name": deal_name,
        "pipeline_stage": result.get("pipeline_stage"),
        "overall_score": result.get("score_summary", {}).get("overall"),
        "deal_readiness": result.get("score_summary", {}).get("deal_readiness"),
        "documents_uploaded": len(raw_files),
        "documents_parsed": len(raw_docs),
        "documents_processed": len(extractions),
        # Full, categorized error reporting
        "errors": all_errors,
        "ingest_errors": ingest_errors,
        "classification_errors": classification_errors,
        "extraction_errors": extraction_errors,
        "pipeline_errors": pipeline_errors,
        "synthesis_error": synthesis_error,
        "document_trace": doc_trace,
        # Include full data for frontend transformation
        "classified_documents": classified,
        "extractions": extractions,
        "rent_roll_analysis": result.get("rent_roll_analysis", {}),
        "rsf_reconciliation": result.get("rsf_reconciliation", {}),
        "red_flags_result": result.get("red_flags_result", {}),
        "score_summary": result.get("score_summary", {}),
        "synthesis": result.get("synthesis", {}),
        "completeness_result": result.get("completeness_result", {}),
    }


@app.get("/deals/{deal_id}", response_model=AnalysisResult)
async def get_deal_analysis(deal_id: str) -> AnalysisResult:
    """Get the analysis result for a deal."""
    if deal_id not in processor.deals:
        raise HTTPException(status_code=404, detail="Deal analysis not found")
    return processor.deals[deal_id]["result"]


@app.get("/deals/{deal_id}/raw")
async def get_deal_raw_data(deal_id: str) -> dict:
    """Get raw analysis data for debugging/detailed view."""
    if deal_id not in processor.deals:
        raise HTTPException(status_code=404, detail="Deal analysis not found")
    return processor.deals[deal_id]["raw_data"]


@app.delete("/documents/{document_id}")
async def delete_document(document_id: str) -> dict:
    """Delete an uploaded document."""
    if document_id not in processor.documents:
        raise HTTPException(status_code=404, detail="Document not found")
    del processor.documents[document_id]
    return {"message": "Document deleted", "document_id": document_id}


@app.get("/agents")
async def list_agents() -> dict:
    """List available AI agents and their capabilities."""
    return {
        "agents": [
            {
                "name": "DocumentClassifierAgent",
                "description": "Classifies documents by type (lease, rent roll, BOMA, etc.)",
                "input": "Document text or file",
                "output": "Document type, confidence, metadata"
            },
            {
                "name": "LeaseAbstractionAgent",
                "description": "Extracts 40+ structured fields from lease documents",
                "input": "Lease document text",
                "output": "Structured lease abstract with all key terms"
            },
            {
                "name": "RentRollAgent",
                "description": "Parses and normalizes rent roll data",
                "input": "Rent roll (Excel/PDF)",
                "output": "Normalized tenant list, summary metrics, issues"
            },
            {
                "name": "RSFReconciliationAgent",
                "description": "Reconciles square footage across sources",
                "input": "Rent roll, leases, BOMA measurement",
                "output": "Variance analysis, revenue impact"
            },
            {
                "name": "RedFlagDetectionAgent",
                "description": "Identifies deal risks and issues",
                "input": "All analysis data",
                "output": "Categorized red flags with severity and actions"
            },
            {
                "name": "RiskScoringAgent",
                "description": "Generates comprehensive deal score (0-100)",
                "input": "Complete deal analysis",
                "output": "Deal score, tier, sub-scores, recommendations"
            }
        ]
    }
