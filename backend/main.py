import fastapi
import fastapi.middleware.cors
from fastapi import UploadFile, File, HTTPException, Form
from typing import Optional, Annotated
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
from services.pipeline import CREPipeline
from services.langgraph_pipeline import CRELangGraphPipeline
from config.extraction_prompts import DOC_TYPES

# Initialize pipelines
pipeline = CREPipeline()
langgraph_pipeline = CRELangGraphPipeline()

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


@app.post("/analyze", response_model=AnalysisResponse)
async def run_analysis(request: AnalysisRequest) -> AnalysisResponse:
    """
    Run full AI analysis pipeline on uploaded documents.
    
    This orchestrates all AI agents:
    1. Document Classification
    2. Lease Abstraction
    3. Rent Roll Analysis
    4. RSF Reconciliation
    5. Red Flag Detection
    6. Risk Scoring
    """
    # Validate documents exist
    missing = [d for d in request.documents if d not in processor.documents]
    if missing:
        raise HTTPException(
            status_code=400, 
            detail=f"Documents not found: {missing}"
        )
    
    try:
        result = await processor.run_full_analysis(
            deal_id=request.deal_id,
            document_ids=request.documents
        )
        
        return AnalysisResponse(
            deal_id=request.deal_id,
            status=ProcessingStatus.COMPLETED,
            message="Analysis completed successfully",
            result=result
        )
    except Exception as e:
        return AnalysisResponse(
            deal_id=request.deal_id,
            status=ProcessingStatus.FAILED,
            message=f"Analysis failed: {str(e)}",
            result=None
        )


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


@app.post("/analyze/files")
async def analyze_files(
    files: list[UploadFile] = File(...),
    deal_name: Annotated[Optional[str], Form()] = None,
    property_appraiser_sf: Annotated[Optional[str], Form()] = None,
    use_langgraph: bool = True
) -> dict:
    """
    MAIN ENTRY POINT - Upload any documents and get RSF analysis.
    
    Just upload files - the system figures out everything:
    1. Auto-detects file type (PDF, Excel, image)
    2. Auto-determines if OCR is needed
    3. Auto-classifies document type
    4. Extracts relevant data
    5. Compares against Property Appraiser baseline SF
    6. Produces report with RSF discrepancies and recovery opportunity
    
    Args:
        files: Documents to analyze
        deal_name: Optional name for this analysis
        property_appraiser_sf: Official SF from County Property Appraiser (the baseline for comparison)
        use_langgraph: If True, uses LangGraph pipeline with full tracing (default)
    
    Returns analysis showing which properties may be underpaying on SF.
    The response includes a `trace_log` array showing each pipeline step.
    """
    try:
        # Read all uploaded files
        file_data = []
        for f in files:
            content = await f.read()
            file_data.append({
                "filename": f.filename,
                "content": content,
                "content_type": f.content_type,
            })
        
        # Parse Property Appraiser SF baseline
        pa_sf = None
        if property_appraiser_sf:
            try:
                pa_sf = float(property_appraiser_sf.replace(',', ''))
            except ValueError:
                pass
        
        # Run pipeline (LangGraph has tracing built-in)
        if use_langgraph:
            result = await langgraph_pipeline.analyze(file_data, deal_name, pa_sf)
        else:
            result = await pipeline.analyze(file_data, deal_name, pa_sf)
        
        return result
        
    except Exception as e:
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


@app.post("/pipeline/run")
async def run_pipeline(deal_name: str, documents: list[dict]) -> dict:
    """
    Legacy endpoint - Run the pipeline with pre-extracted document content.
    
    For most use cases, use POST /analyze/files instead.
    """
    try:
        result = await pipeline.analyze(documents, deal_name)
        return result
    except Exception as e:
        import traceback
        return {
            "success": False,
            "deal_name": deal_name,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }


@app.get("/pipeline/doc-types")
async def list_doc_types() -> dict:
    """List all supported document types for the pipeline."""
    return {
        "doc_types": DOC_TYPES,
        "descriptions": {
            "LEASE": "Full executed lease agreement",
            "LEASE_ABSTRACT": "Summary of lease terms",
            "RENT_ROLL": "Tenant roster with rents (PDF)",
            "RENT_ROLL_XLSX": "Tenant roster from spreadsheet",
            "BOMA": "BOMA measurement certificate",
            "FINANCIAL_MODEL": "Underwriting model with projections",
            "CAM_RECONCILIATION": "CAM expense reconciliation",
            "MANAGEMENT_REPORT": "Property management report",
            "COUNTY_PA": "County property appraiser record",
        }
    }


@app.get("/agents")
async def list_agents() -> dict:
    """
    List the collapsed pipeline stages (replaces 76 n8n nodes with 15).
    
    Based on the CRE Document Intelligence v2 technical reference.
    """
    return {
        "pipeline_architecture": "Collapsed 15-node design",
        "original_nodes": 76,
        "collapsed_nodes": 15,
        "stages": [
            {
                "stage": 1,
                "name": "File Extraction",
                "node": "Universal File Ingestion",
                "description": "Detects file type, handles OCR, loops over all files dynamically",
                "replaces": "Extract Pages from PDF, Extract_Rent_Roll, Extract_Lease×8, Extract_BOMA, Handle Image Upload"
            },
            {
                "stage": 2,
                "name": "Classification",
                "node": "Classify Documents",
                "description": "Single node classifies all documents into 9 types",
                "replaces": "Build Classification Payload, Claude - Classify Doc, Parse Classification, Route by Doc Type"
            },
            {
                "stage": 3,
                "name": "Extraction",
                "node": "Extract Documents (config-driven)",
                "description": "ONE node with config map handles all 9 doc types",
                "replaces": "27 extraction lane nodes (Build Payload ×9, Claude Call ×9, Parse ×9)"
            },
            {
                "stage": 4,
                "name": "Synthesis",
                "node": "Synthesize Deal",
                "description": "Cross-document analysis, RSF reconciliation, scoring",
                "replaces": "Build Synthesis Payload, Claude - Synthesize Deal, Parse Synthesis"
            },
            {
                "stage": 5,
                "name": "Verification",
                "node": "Verify Analysis",
                "description": "Arithmetic checks, confidence thresholds",
                "replaces": "Arithmetic Verification, Flatten Fields, Independent Verification, Apply Confidence"
            },
            {
                "stage": 6,
                "name": "Output",
                "node": "Format Output",
                "description": "Structures data for all 6 sheet tabs",
                "replaces": "Build Deal Snapshot Rows, Build Audit Log Rows, Build Rent Rows, Build Lease Audit Rows, Build Risk Dashboard"
            }
        ],
        "doc_types_supported": DOC_TYPES,
        "key_outputs": [
            "Deal Score (0-100) with tier classification",
            "RSF Reconciliation across all sources",
            "Red Flags by severity (CRITICAL, HIGH, MEDIUM, LOW)",
            "WALT calculation and lease expiry schedule",
            "What To Get Next prioritized list",
            "RSF Recovery Opportunity with dollar estimate"
        ]
    }
