"""
CRE deal analysis pipeline (LangGraph).

  ingest_documents      parse text; OCR scans and images with Claude
  classify_documents    classify every document concurrently
  extract_document ×N   extract each document against its schema (fan-out)
  compute_metrics       tenant roster, RSF, WALT, AR, arithmetic checks — in code
  synthesize            Claude's qualitative review: lease risks, summary, requests
  build_report          score + red flags + dashboard payload — in code

Run it with `await graph.ainvoke(state)`; the nodes are async.
"""

import asyncio
import logging
import os
from datetime import date, datetime, timezone

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

from state import CREPipelineState, SingleDocumentState
from agents.document_parsing import DocumentParsingAgent
from agents.ocr_agent import OCRAgent
from agents.universal_extractor import UniversalExtractor
from agents.synthesis import SynthesisAgent
from agents.base import fatal_api_message
from services.deal_metrics import compute_metrics as _compute_metrics, build_report as _build_report, public_metrics

log = logging.getLogger("cre.pipeline")

# LangSmith tracing only when a key is configured; otherwise it just logs auth errors.
if os.environ.get("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_PROJECT", "CRE Don Project")
else:
    os.environ["LANGSMITH_TRACING"] = "false"

MAX_TEXT_CHARS = 150_000

_parser = DocumentParsingAgent()
_ocr = OCRAgent()
_extractor = UniversalExtractor()
_synthesizer = SynthesisAgent()


async def ingest_documents(state: CREPipelineState) -> dict:
    async def ingest_one(index: int, filename: str, file_bytes: bytes):
        content_type = state["file_content_types"].get(filename, "application/octet-stream")
        parsed = _parser.check(filename=filename, file_content=file_bytes, content_type=content_type)
        if not parsed.is_parseable:
            return None, f"{filename}: {parsed.reason}"
        text, ocr_note = parsed.extracted_text, None
        if parsed.needs_ocr:
            ocr = await _ocr.process(file_content=file_bytes, filename=filename, page_count=parsed.page_count)
            if not ocr["document_readable"]:
                return None, f"{filename}: OCR failed — {'; '.join(ocr['ocr_issues_found'])}"
            text = ocr["cleaned_text"]
            ocr_note = "; ".join(ocr["ocr_issues_found"]) or None
        return {
            "doc_id": f"doc-{index + 1}", "deal_name": state["deal_name"], "filename": filename,
            "content_type": content_type, "file_type": parsed.file_type,
            "extracted_text": text[:MAX_TEXT_CHARS], "page_count": parsed.page_count,
            "ocr_performed": parsed.needs_ocr, "ocr_note": ocr_note, "parse_method": parsed.method,
        }, None

    results = await asyncio.gather(
        *[ingest_one(i, name, data) for i, (name, data) in enumerate(state["raw_files"].items())],
        return_exceptions=True,
    )
    docs, errors = [], []
    for (name, _), result in zip(state["raw_files"].items(), results):
        if isinstance(result, Exception) and fatal_api_message(result):
            raise result
        if isinstance(result, Exception):
            errors.append(f"{name}: {result}")
            continue
        doc, err = result
        if doc:
            docs.append(doc)
        if err:
            errors.append(err)
    return {"raw_documents": docs, "ingest_errors": errors, "pipeline_stage": "ingested"}


async def classify_documents(state: CREPipelineState) -> dict:
    async def classify_one(doc):
        try:
            result = await _extractor.classify_document(
                text=doc["extracted_text"], filename=doc["filename"], mime_type=doc.get("content_type"))
            return {**doc, "doc_type": result["doc_type"],
                    "classification_confidence": result["confidence"],
                    "classification_reasoning": result["reasoning"]}, None
        except Exception as e:
            if fatal_api_message(e):
                raise
            return ({**doc, "doc_type": "OTHER", "classification_confidence": 0.0,
                     "classification_reasoning": str(e)}, f"{doc['filename']}: classification failed — {e}")

    results = await asyncio.gather(*[classify_one(d) for d in state["raw_documents"]])
    return {"classified_documents": [d for d, _ in results],
            "pipeline_errors": [e for _, e in results if e],
            "pipeline_stage": "classified"}


def fan_out_extractions(state: CREPipelineState):
    sends = [
        Send("extract_document", SingleDocumentState(
            doc_id=d["doc_id"], deal_name=d["deal_name"], filename=d["filename"],
            doc_type=d["doc_type"], extracted_text=d["extracted_text"]))
        for d in state["classified_documents"] if d["doc_type"] != "OTHER"
    ]
    return sends or ["compute_metrics"]


async def extract_document(state: SingleDocumentState) -> dict:
    try:
        result = await _extractor.extract_document(
            text=state["extracted_text"], doc_type=state["doc_type"], doc_id=state["doc_id"],
            deal_name=state["deal_name"], filename=state["filename"])
    except Exception as e:
        if fatal_api_message(e):
            raise
        result = {"doc_id": state["doc_id"], "doc_type": state["doc_type"], "filename": state["filename"],
                  "deal_name": state["deal_name"], "extraction": {}, "parse_error": str(e),
                  "pipeline_stage": "extraction_failed"}
    errors = [f"{state['filename']}: {result['parse_error']}"] if result.get("parse_error") else []
    return {"extractions": [result], "pipeline_errors": errors}


def compute_metrics(state: CREPipelineState) -> dict:
    as_of = date.fromisoformat(state["as_of"]) if state.get("as_of") else None
    return {"metrics": _compute_metrics(state["extractions"], as_of=as_of), "pipeline_stage": "measured"}


async def synthesize(state: CREPipelineState) -> dict:
    if not state["extractions"]:
        return {"synthesis": {}, "pipeline_stage": "synthesis_skipped"}
    try:
        result = await _synthesizer.synthesize_deal(
            extractions=state["extractions"], metrics=public_metrics(state["metrics"]),
            deal_name=state["deal_name"])
        return {"synthesis": result, "pipeline_stage": "synthesized"}
    except Exception as e:
        if fatal_api_message(e):
            raise
        log.exception("synthesis failed")
        # The computed report still stands without the qualitative review.
        return {"synthesis": {}, "pipeline_stage": "synthesis_failed",
                "pipeline_errors": [f"AI review unavailable: {e}"]}


def build_report(state: CREPipelineState) -> dict:
    completed_at = datetime.now(timezone.utc).isoformat()
    report = _build_report(
        deal_id=state["deal_id"], deal_name=state["deal_name"],
        classified_documents=state["classified_documents"], extractions=state["extractions"],
        ingest_errors=state["ingest_errors"], metrics=state["metrics"], synthesis=state.get("synthesis"),
        pipeline_errors=state["pipeline_errors"], files_uploaded=len(state["raw_files"]),
        completed_at=completed_at)
    return {"report": report, "completed_at": completed_at, "pipeline_stage": "completed"}


def build_graph():
    builder = StateGraph(CREPipelineState)
    builder.add_node("ingest_documents", ingest_documents)
    builder.add_node("classify_documents", classify_documents)
    builder.add_node("extract_document", extract_document)
    builder.add_node("compute_metrics", compute_metrics)
    builder.add_node("synthesize", synthesize)
    builder.add_node("build_report", build_report)
    builder.add_edge(START, "ingest_documents")
    builder.add_edge("ingest_documents", "classify_documents")
    builder.add_conditional_edges("classify_documents", fan_out_extractions,
                                  ["extract_document", "compute_metrics"])
    builder.add_edge("extract_document", "compute_metrics")
    builder.add_edge("compute_metrics", "synthesize")
    builder.add_edge("synthesize", "build_report")
    builder.add_edge("build_report", END)
    return builder.compile()


graph = build_graph()
