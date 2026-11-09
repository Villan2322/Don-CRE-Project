"""
CRE Document Intelligence server.

One process serves both the API (under /api) and the built dashboard (static
files from STATIC_DIR). An analysis runs as a background job: POST /api/analyze
returns a job id right away, and the browser polls GET /api/jobs/{id}. Every
request stays short, so no proxy timeout can cut off a long run.

Jobs live in memory. Run a single instance; a restart drops in-flight jobs
(finished results are already saved in the user's browser).
"""

import asyncio
import logging
import os
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from graph import graph
from state import initial_state

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cre.api")

MAX_FILES = int(os.environ.get("MAX_FILES", 25))
MAX_UPLOAD_MB = float(os.environ.get("MAX_UPLOAD_MB", 100))
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT_ANALYSES", 3))
JOB_TTL_SECONDS = 6 * 3600
STATIC_DIR = os.environ.get("STATIC_DIR", str(Path(__file__).resolve().parent.parent / "frontend" / "out"))

# What the user sees while each step runs (keyed by the step that just finished).
NEXT_STAGE = {
    "ingest_documents": "Classifying documents",
    "classify_documents": "Extracting data",
    "extract_document": "Extracting data",
    "compute_metrics": "AI review",
    "synthesize": "Scoring",
    "build_report": "Finishing",
}

app = FastAPI(
    title="CRE Document Intelligence",
    description="AI-assisted document analysis for commercial real estate due diligence",
    version="3.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o],
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
_jobs: dict[str, dict] = {}
_slots = asyncio.Semaphore(MAX_CONCURRENT)
_tasks: set[asyncio.Task] = set()


def _prune_jobs() -> None:
    cutoff = time.time() - JOB_TTL_SECONDS
    for job_id in [j for j, job in _jobs.items() if job["created"] < cutoff]:
        _jobs.pop(job_id, None)


async def _run(job_id: str, state: dict) -> None:
    job = _jobs[job_id]
    try:
        async with _slots:
            job.update(status="running", stage="Reading documents")
            final = None
            async for mode, chunk in graph.astream(state, stream_mode=["updates", "values"]):
                if mode == "updates":
                    for node in chunk:
                        job["stage"] = NEXT_STAGE.get(node, job["stage"])
                else:
                    final = chunk
        job.update(status="done", stage="Done", result={
            "deal_id": job_id,
            "deal_name": final["deal_name"],
            "pipeline_stage": final.get("pipeline_stage"),
            "errors": final.get("ingest_errors", []) + final.get("pipeline_errors", []),
            "analysis": final.get("report"),
        })
        log.info("job %s done: %s", job_id, final.get("pipeline_stage"))
    except Exception as e:  # never leave a job stuck in "running"
        log.exception("job %s failed", job_id)
        job.update(status="failed", error=f"The analysis failed: {e}")


@api.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "anthropic_key_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "jobs_in_memory": len(_jobs),
    }


@api.post("/analyze", status_code=202)
async def analyze_deal(
    deal_name: str = Form(...),
    files: list[UploadFile] = File(...),
    as_of: Optional[str] = Form(None),
) -> dict:
    """Start an analysis. Poll GET /api/jobs/{job_id} for the result."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise HTTPException(503, "ANTHROPIC_API_KEY is not set on the server.")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Upload at most {MAX_FILES} files per analysis.")
    if as_of:
        try:
            date.fromisoformat(as_of)
        except ValueError:
            raise HTTPException(400, "as_of must be YYYY-MM-DD")

    raw_files: dict[str, bytes] = {}
    content_types: dict[str, str] = {}
    total = 0
    for f in files:
        if not f.filename:
            continue
        name = f.filename
        if name in raw_files:  # two files with the same name — keep both
            stem, dot, ext = name.rpartition(".")
            name = f"{stem or ext} ({len(raw_files) + 1}){dot}{ext if stem else ''}"
        data = await f.read()
        total += len(data)
        if total > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Upload is over {MAX_UPLOAD_MB:g} MB.")
        raw_files[name] = data
        content_types[name] = f.content_type or "application/octet-stream"
    if not raw_files:
        raise HTTPException(400, "No files provided")

    _prune_jobs()
    job_id = str(uuid.uuid4())
    state = initial_state(job_id, deal_name.strip() or "Untitled Deal", raw_files, content_types, as_of)
    _jobs[job_id] = {"status": "queued", "stage": "Queued", "created": time.time(), "result": None, "error": None}
    task = asyncio.create_task(_run(job_id, state))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    log.info("job %s queued: %s, %d file(s), %.1f MB", job_id, deal_name, len(raw_files), total / 1e6)
    return {"job_id": job_id, "status": "queued"}


@api.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return {k: v for k, v in job.items() if not k.startswith("_") and k != "created"}


app.include_router(api)


@app.get("/health")
async def root_health() -> dict:
    """Liveness check for container platforms."""
    return {"status": "ok"}


# The dashboard. Mounted last so /api routes win.
if Path(STATIC_DIR, "index.html").exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")
else:
    log.warning("No dashboard build at %s — serving the API only", STATIC_DIR)
