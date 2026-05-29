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
from .graph import graph

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

    result = graph.invoke(initial_state)
    processor.deals[deal_id] = {"result": result, "raw_data": result}

    # Return FULL result directly since serverless can't persist state between calls
    return {
        "deal_id": deal_id,
        "deal_name": deal_name,
        "pipeline_stage": result.get("pipeline_stage"),
        "overall_score": result.get("score_summary", {}).get("overall"),
        "deal_readiness": result.get("score_summary", {}).get("deal_readiness"),
        "documents_processed": len(result.get("extractions", [])),
        "errors": result.get("pipeline_errors", []),
        # Include full data for frontend transformation
        "classified_documents": result.get("classified_documents", []),
        "extractions": result.get("extractions", []),
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
