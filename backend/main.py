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
        status=doc.status
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
    Run the full LangGraph pipeline on one or more uploaded files.

    Accepts multipart/form-data with:
    - deal_name: string
    - files: one or more file uploads
    """
    deal_id = str(uuid.uuid4())
    raw_files: dict[str, bytes] = {}
    content_types: dict[str, str] = {}

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

    result = await graph.ainvoke(initial_state)
    if not hasattr(processor, 'deals'):
        processor.deals = {}
    processor.deals[deal_id] = {"result": result, "raw_data": result}

    all_errors = (
        result.get("ingest_errors", [])
        + result.get("classification_errors", [])
        + result.get("extraction_errors", [])
        + result.get("pipeline_errors", [])
    )

    classified = result.get("classified_documents", [])
    extractions = result.get("extractions", [])

    return {
        "deal_id": deal_id,
        "pipeline_stage": result.get("pipeline_stage"),
        "overall_score": result.get("score_summary", {}).get("overall"),
        "deal_readiness": result.get("score_summary", {}).get("deal_readiness"),
        "documents_ingested": len(result.get("raw_documents", [])),
        "documents_classified": len(classified),
        "documents_processed": len(extractions),
        "classifications": [
            {
                "filename": d["filename"],
                "doc_type": d["doc_type"],
                "confidence": d["classification_confidence"],
            }
            for d in classified
        ],
        "extraction_results": [
            {
                "filename": e["filename"],
                "doc_type": e["doc_type"],
                "success": not e.get("parse_error"),
                "error": e.get("parse_error"),
            }
            for e in extractions
        ],
        "synthesis": result.get("synthesis", {}),
        "score_summary": result.get("score_summary", {}),
        "errors": all_errors,
    }


@app.get("/deals/{deal_id}")
async def get_deal_analysis(deal_id: str) -> dict:
    """Get the analysis result for a deal."""
    deals = getattr(processor, 'deals', {})
    if deal_id not in deals:
        raise HTTPException(status_code=404, detail="Deal analysis not found")
    return deals[deal_id]["result"]


@app.get("/deals/{deal_id}/raw")
async def get_deal_raw_data(deal_id: str) -> dict:
    """Get raw analysis data for debugging/detailed view."""
    deals = getattr(processor, 'deals', {})
    if deal_id not in deals:
        raise HTTPException(status_code=404, detail="Deal analysis not found")
    return deals[deal_id]["raw_data"]


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
        "pipeline": [
            {
                "stage": 1,
                "name": "DocumentParsingAgent",
                "description": "Inspects the raw file to determine whether it is text-native or scanned. "
                               "Extracts text directly for native PDFs, Excel, and CSV. "
                               "Routes scanned/image PDFs to the OCRAgent.",
                "input": "Raw file bytes + filename + content-type",
                "output": "ParseabilityResult: is_parseable, needs_ocr, extracted_text, file_type, confidence"
            },
            {
                "stage": 2,
                "name": "OCRAgent",
                "description": "Fires only when the document is a scanned/image-based PDF. "
                               "Renders each page to an image via PyMuPDF, runs Tesseract OCR, "
                               "then passes the raw OCR output through the LLM to clean, "
                               "correct, and restructure the text before downstream processing.",
                "input": "Raw PDF bytes (scanned)",
                "output": "cleaned_text, raw_ocr_text, confidence, ocr_issues_found, document_readable"
            },
            {
                "stage": 3,
                "name": "DocumentClassifierAgent",
                "description": "Classifies readable text into CRE document types "
                               "(LEASE, RENT_ROLL, BOMA_MEASUREMENT, OPERATING_STATEMENT, etc.) "
                               "and assesses completeness of the due diligence package.",
                "input": "Cleaned document text",
                "output": "document_type, confidence, metadata, completeness_score"
            },
            {
                "stage": 4,
                "name": "LeaseAbstractionAgent",
                "description": "Extracts 40+ structured fields from lease documents.",
                "input": "Lease document text",
                "output": "Structured lease abstract with all key terms"
            },
            {
                "stage": 4,
                "name": "RentRollAgent",
                "description": "Parses and normalizes rent roll data, validates against leases, "
                               "calculates WALT and occupancy.",
                "input": "Rent roll text (from Excel or PDF)",
                "output": "Normalized tenant list, summary metrics, issues"
            },
            {
                "stage": 5,
                "name": "RSFReconciliationAgent",
                "description": "Reconciles RSF across rent roll, leases, and BOMA. "
                               "Flags variances >2% and estimates revenue impact.",
                "input": "Rent roll data, lease abstracts, BOMA report",
                "output": "Variance analysis, per-tenant discrepancies, revenue impact"
            },
            {
                "stage": 6,
                "name": "RedFlagDetectionAgent",
                "description": "Identifies deal risks across 5 categories with severity scoring.",
                "input": "All analysis data",
                "output": "Categorized red flags with severity and recommended actions"
            },
            {
                "stage": 7,
                "name": "RiskScoringAgent",
                "description": "Produces a composite 0-100 deal score across 6 weighted categories.",
                "input": "Complete deal analysis",
                "output": "Deal score, tier, sub-scores, recommendations"
            }
        ]
    }
