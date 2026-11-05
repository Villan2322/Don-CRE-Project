import logging
import os
import uuid
from datetime import date
from typing import Optional

import fastapi
import fastapi.middleware.cors
from fastapi import File, Form, HTTPException, UploadFile

from graph import graph
from state import initial_state

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cre.api")

MAX_FILES = 25

app = fastapi.FastAPI(
    title="CRE Document Intelligence API",
    description="AI-assisted document analysis for commercial real estate due diligence",
    version="2.0.0",
)

app.add_middleware(
    fastapi.middleware.cors.CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "cre-document-intelligence",
        "anthropic_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.post("/analyze")
async def analyze_deal(
    deal_name: str = Form(...),
    files: list[UploadFile] = File(...),
    as_of: Optional[str] = Form(None),
) -> dict:
    """
    Run the full pipeline on a document package and return the dashboard payload.

    The response carries everything the dashboard needs; nothing is stored
    server-side (serverless functions don't keep state between calls).
    """
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=503, detail="ANTHROPIC_API_KEY is not set on the server.")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Upload at most {MAX_FILES} files per analysis.")
    if as_of:
        try:
            date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD")

    raw_files: dict[str, bytes] = {}
    content_types: dict[str, str] = {}
    for f in files:
        if not f.filename:
            continue
        name = f.filename
        if name in raw_files:  # two files with the same name — keep both
            stem, dot, ext = name.rpartition(".")
            name = f"{stem or ext} ({len(raw_files) + 1}){dot}{ext if stem else ''}"
        raw_files[name] = await f.read()
        content_types[name] = f.content_type or "application/octet-stream"
    if not raw_files:
        raise HTTPException(status_code=400, detail="No files provided")

    deal_id = str(uuid.uuid4())
    log.info("analysis %s started: %s, %d file(s)", deal_id, deal_name, len(raw_files))
    result = await graph.ainvoke(
        initial_state(deal_id, deal_name.strip() or "Untitled Deal", raw_files, content_types, as_of))
    log.info("analysis %s finished: stage=%s errors=%d", deal_id,
             result.get("pipeline_stage"), len(result.get("pipeline_errors", [])))

    return {
        "deal_id": deal_id,
        "deal_name": result["deal_name"],
        "pipeline_stage": result.get("pipeline_stage"),
        "errors": result.get("ingest_errors", []) + result.get("pipeline_errors", []),
        "analysis": result.get("report"),
    }


@app.get("/agents")
async def list_agents() -> dict:
    return {"pipeline": [
        {"step": "Ingest", "description": "Reads text from PDFs, spreadsheets, and CSVs; OCRs scans and images with Claude"},
        {"step": "Classify", "description": "Identifies each document type (lease, rent roll, BOMA, management report, ...)"},
        {"step": "Extract", "description": "Pulls structured fields from each document against a fixed schema"},
        {"step": "Measure", "description": "Computes tenant roster, RSF reconciliation, WALT, AR, and arithmetic checks in code"},
        {"step": "Review", "description": "Claude flags lease-level risks and recommends what to request next"},
        {"step": "Score", "description": "Six-category 0-100 score computed in code, with a reason for every point"},
    ]}
