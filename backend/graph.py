import os
import asyncio
from datetime import datetime, timezone
from langgraph.graph import StateGraph, START, END
from langgraph.types import Send


def configure_langsmith_tracing():
    """
    Configure LangSmith tracing at runtime.
    Must be called BEFORE graph invocation in serverless environments
    where env vars are loaded after module import.
    """
    # Map LANGSMITH_* to LANGCHAIN_* (LangGraph uses LANGCHAIN_* internally)
    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get("LANGCHAIN_API_KEY")
    if api_key:
        os.environ["LANGCHAIN_API_KEY"] = api_key
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        
        # Project name (strip quotes if present)
        project = os.environ.get("LANGSMITH_PROJECT") or os.environ.get("LANGCHAIN_PROJECT") or "cre-document-intelligence"
        os.environ["LANGCHAIN_PROJECT"] = project.strip('"\'')
        
        # Endpoint (optional)
        endpoint = os.environ.get("LANGSMITH_ENDPOINT") or os.environ.get("LANGCHAIN_ENDPOINT")
        if endpoint:
            os.environ["LANGCHAIN_ENDPOINT"] = endpoint
        
        print(f"[LANGSMITH] Tracing enabled - Project: {os.environ['LANGCHAIN_PROJECT']}")
        return True
    else:
        print("[LANGSMITH] No API key found - tracing disabled")
        return False

# Support both package imports (when run as module) and direct imports (for tests)
try:
    from .state import CREPipelineState, SingleDocumentState
    from .agents.document_parsing import DocumentParsingAgent
    from .agents.ocr_agent import OCRAgent
    from .agents.universal_extractor import UniversalExtractor
    from .agents.synthesis import SynthesisAgent, ArithmeticVerificationAgent
    from .agents.document_classifier import DocumentClassifierAgent
    from .agents.rsf_reconciliation import RSFReconciliationAgent
    from .agents.red_flag_detection import RedFlagDetectionAgent
    from .agents.risk_scoring import RiskScoringAgent
    from .agents.document_segmentation import DocumentSegmentationAgent
except ImportError:
    from state import CREPipelineState, SingleDocumentState
    from agents.document_parsing import DocumentParsingAgent
    from agents.ocr_agent import OCRAgent
    from agents.universal_extractor import UniversalExtractor
    from agents.synthesis import SynthesisAgent, ArithmeticVerificationAgent
    from agents.document_classifier import DocumentClassifierAgent
    from agents.rsf_reconciliation import RSFReconciliationAgent
    from agents.red_flag_detection import RedFlagDetectionAgent
    from agents.risk_scoring import RiskScoringAgent
    from agents.document_segmentation import DocumentSegmentationAgent

_parsing_agent = DocumentParsingAgent()
_ocr_agent = OCRAgent()
_segmentation_agent = DocumentSegmentationAgent()
_extractor = UniversalExtractor()
_synthesizer = SynthesisAgent()
_arithmetic = ArithmeticVerificationAgent()
_classifier = DocumentClassifierAgent()
_rsf_agent = RSFReconciliationAgent()
_red_flag_agent = RedFlagDetectionAgent()
_risk_agent = RiskScoringAgent()


async def ingest_documents(state: CREPipelineState) -> dict:
    """
    Ingest and parse documents. For multi-page PDFs, segment into logical sections.
    Each segment becomes a separate document for downstream classification/extraction.
    """
    raw_documents = []
    errors = []
    
    print(f"[INGEST] Starting ingestion of {len(state['raw_files'])} files")
    
    for filename, file_bytes in state["raw_files"].items():
        content_type = state["file_content_types"].get(filename, "application/octet-stream")
        base_doc_id = f"doc-{filename.replace(' ', '_')}-{id(file_bytes)}"
        
        print(f"[INGEST] Processing: {filename} ({len(file_bytes)} bytes, {content_type})")
        
        try:
            parse_result = _parsing_agent.check(
                filename=filename, file_content=file_bytes, content_type=content_type
            )
            
            print(f"[INGEST] Parse result: parseable={parse_result.is_parseable}, type={parse_result.file_type}, needs_ocr={parse_result.needs_ocr}, text_len={len(parse_result.extracted_text)}")
            
            if not parse_result.is_parseable:
                errors.append(f"{filename}: {parse_result.reason}")
                continue
            
            # Extract text (with OCR if needed)
            extracted_text = ""
            ocr_performed = False
            ocr_confidence = None
            
            if parse_result.needs_ocr:
                print(f"[INGEST] Running OCR for {filename}...")
                ocr_result = await _ocr_agent.process(
                    file_content=file_bytes, filename=filename, 
                    page_count=parse_result.page_count
                )
                ocr_performed = True
                ocr_confidence = ocr_result.get("confidence")
                
                print(f"[INGEST] OCR result: readable={ocr_result.get('document_readable')}, confidence={ocr_confidence}, text_len={len(ocr_result.get('cleaned_text', ''))}")
                
                if not ocr_result.get("document_readable", False):
                    errors.append(
                        f"{filename}: OCR failed — {', '.join(ocr_result.get('ocr_issues_found', []))}"
                    )
                    print(f"[INGEST] OCR failed: {ocr_result.get('ocr_issues_found')}")
                    continue
                extracted_text = ocr_result.get("cleaned_text", "")
            else:
                extracted_text = parse_result.extracted_text
            
            print(f"[INGEST] Extracted {len(extracted_text)} chars from {filename}")
            
            # Check if this is a multi-section document that should be segmented
            # Segment if: PDF with 3+ pages OR text with 5000+ chars with section markers
            has_section_markers = any(marker in extracted_text.lower() for marker in [
                'collection report', 'cash receipts', 'disbursements', 
                'ending receivables', 'lease recap', 'rent roll', 'ar aging',
                'income and expense', 'sales volume'
            ])
            
            should_segment = (
                (parse_result.page_count and parse_result.page_count > 3 and parse_result.file_type == "pdf") or
                (len(extracted_text) > 5000 and has_section_markers)
            )
            
            if should_segment:
                # Segment the document into logical sections
                segments = await _segmentation_agent.segment_document(
                    full_text=extracted_text,
                    page_texts=None  # Let the agent split by page markers
                )
                
                # Create a document entry for each segment
                for idx, segment in enumerate(segments):
                    seg_doc_id = f"{base_doc_id}-seg{idx+1}"
                    seg_filename = f"{filename} [Segment {idx+1}: {segment.doc_type}]"
                    
                    raw_documents.append({
                        "doc_id": seg_doc_id,
                        "deal_name": state["deal_name"],
                        "filename": seg_filename,
                        "original_filename": filename,
                        "content_type": content_type,
                        "file_type": parse_result.file_type,
                        "extracted_text": segment.text[:50000],
                        "page_count": segment.end_page - segment.start_page + 1,
                        "start_page": segment.start_page,
                        "end_page": segment.end_page,
                        "needs_ocr": parse_result.needs_ocr,
                        "ocr_performed": ocr_performed,
                        "ocr_confidence": ocr_confidence,
                        "is_parseable": True,
                        "parse_method": parse_result.method,
                        "parse_reason": parse_result.reason,
                        "segment_type_hint": segment.doc_type,
                        "segment_confidence": segment.confidence,
                        "is_segment": True,
                    })
            else:
                # Single document, no segmentation needed
                raw_documents.append({
                    "doc_id": base_doc_id,
                    "deal_name": state["deal_name"],
                    "filename": filename,
                    "original_filename": filename,
                    "content_type": content_type,
                    "file_type": parse_result.file_type,
                    "extracted_text": extracted_text[:50000],
                    "page_count": parse_result.page_count,
                    "needs_ocr": parse_result.needs_ocr,
                    "ocr_performed": ocr_performed,
                    "ocr_confidence": ocr_confidence,
                    "is_parseable": True,
                    "parse_method": parse_result.method,
                    "parse_reason": parse_result.reason,
                    "is_segment": False,
                })
                
        except Exception as e:
            errors.append(f"{filename}: {str(e)}")
    
    return {
        "raw_documents": raw_documents, 
        "ingest_errors": errors, 
        "pipeline_stage": "ingested"
    }


async def classify_documents(state: CREPipelineState) -> dict:
    """
    Classify each document (or segment) by type.
    Uses segment type hints when available from segmentation.
    """
    classified = []
    errors = []

    async def classify_one(doc):
        try:
            # If this is a segment with a high-confidence type hint, use it
            segment_hint = doc.get("segment_type_hint")
            segment_conf = doc.get("segment_confidence", 0)
            
            if segment_hint and segment_hint != "UNKNOWN" and segment_conf > 0.7:
                # Use the segment type hint directly
                return {
                    **doc, 
                    "doc_type": segment_hint,
                    "classification_confidence": segment_conf,
                    "classification_reasoning": f"Segment auto-classified as {segment_hint} with confidence {segment_conf:.2f}",
                    "classification_source": "segmentation"
                }
            
            # Otherwise, run full classification
            result = await _extractor.classify_document(
                text=doc["extracted_text"], 
                filename=doc["filename"],
                mime_type=doc.get("content_type")
            )
            
            return {
                **doc, 
                "doc_type": result["doc_type"],
                "classification_confidence": result["confidence"],
                "classification_reasoning": result.get("reasoning", ""),
                "classification_source": "llm"
            }
        except Exception as e:
            errors.append(f"{doc['filename']}: {str(e)}")
            return {
                **doc, 
                "doc_type": "UNKNOWN", 
                "classification_confidence": 0.0,
                "classification_reasoning": str(e),
                "classification_source": "error"
            }

    results = await asyncio.gather(*[classify_one(doc) for doc in state["raw_documents"]])
    return {
        "classified_documents": list(results), 
        "classification_errors": errors,
        "pipeline_stage": "classified"
    }


def fan_out_extractions(state: CREPipelineState) -> list[Send]:
    return [
        Send("extract_single_document", SingleDocumentState(
            doc_id=doc["doc_id"], deal_name=doc["deal_name"],
            filename=doc["filename"], doc_type=doc["doc_type"],
            extracted_text=doc["extracted_text"],
            ocr_performed=doc["ocr_performed"],
            classification_confidence=doc["classification_confidence"],
        ))
        for doc in state["classified_documents"]
        if doc["doc_type"] != "UNKNOWN"
    ]


async def extract_single_document(state: SingleDocumentState) -> dict:
    try:
        result = await _extractor.extract_document(
            text=state["extracted_text"], doc_type=state["doc_type"],
            doc_id=state["doc_id"], deal_name=state["deal_name"],
            filename=state["filename"])
        extraction = result.get("extraction", {})
        enriched = extraction.pop("_enriched", None)
        missing = extraction.pop("_missing_fields", [])
        abstract_complete = extraction.pop("_abstract_complete", True)
        return {
            "extractions": [{
                "doc_id": state["doc_id"], "deal_name": state["deal_name"],
                "filename": state["filename"], "doc_type": state["doc_type"],
                "extraction": extraction, "parse_error": result.get("parse_error"),
                "pipeline_stage": result.get("pipeline_stage", "extracted"),
                "extraction_timestamp": result.get("extraction_timestamp", datetime.now(timezone.utc).isoformat()),
                "enriched": enriched, "missing_fields": missing,
                "abstract_complete": abstract_complete,
            }],
            "extraction_errors": ([f"{state['filename']}: {result['parse_error']}"]
                                   if result.get("parse_error") else []),
        }
    except Exception as e:
        return {
            "extractions": [{"doc_id": state["doc_id"], "deal_name": state["deal_name"],
                              "filename": state["filename"], "doc_type": state["doc_type"],
                              "extraction": {}, "parse_error": str(e),
                              "pipeline_stage": "extraction_failed",
                              "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
                              "enriched": None, "missing_fields": [], "abstract_complete": False}],
            "extraction_errors": [f"{state['filename']}: {str(e)}"],
        }


def calculate_data_completeness_score(doc_types: list[str]) -> tuple[int, list[str]]:
    """Calculate data completeness score based on document categories present."""
    categories = {
        "tenant_rent": ["RENT_ROLL", "RENT_ROLL_XLSX"],
        "lease_terms": ["LEASE", "LEASE_ABSTRACT", "LEASE_RECAP"],
        "measurements": ["BOMA", "COUNTY_PA"],
        "financials": ["MANAGEMENT_REPORT", "FINANCIAL_MODEL", "DISBURSEMENTS", "INCOME_EXPENSE"],
        "receivables": ["ENDING_RECEIVABLES", "AR_AGING", "CAM_RECONCILIATION"],
    }
    categories_found = []
    for cat_name, cat_types in categories.items():
        if any(dt in doc_types for dt in cat_types):
            categories_found.append(cat_name)
    return min(len(categories_found) * 4, 20), categories_found


async def synthesize(state: CREPipelineState) -> dict:
    try:
        result = await _synthesizer.synthesize_deal(
            extractions=state["extractions"], deal_name=state["deal_name"])
        if result.get("_parse_error"):
            return {"synthesis": {}, "rsf_recovery": {}, "score_summary": {},
                    "synthesis_error": result["_parse_error"],
                    "pipeline_stage": "synthesis_failed",
                    "pipeline_errors": [f"Synthesis error: {result['_parse_error']}"]}
        
        # Get doc types from extractions for deterministic scoring
        doc_types = list(set(ext["doc_type"] for ext in state["extractions"]))
        print(f"[SCORING] Doc types for scoring: {doc_types}")
        
        # Calculate deterministic data completeness score
        data_completeness, categories_found = calculate_data_completeness_score(doc_types)
        print(f"[SCORING] Categories found: {categories_found} = {data_completeness}/20 pts")
        
        # Override the LLM's data_completeness with deterministic calculation
        score_summary = result.get("score_summary", {})
        synthesis = result.get("synthesis", {})
        
        if synthesis.get("deal_score", {}).get("sub_scores"):
            old_score = synthesis["deal_score"]["sub_scores"].get("data_completeness", 0)
            synthesis["deal_score"]["sub_scores"]["data_completeness"] = data_completeness
            
            # Recalculate overall score
            sub_scores = synthesis["deal_score"]["sub_scores"]
            new_overall = sum([
                sub_scores.get("data_completeness", 0),
                sub_scores.get("rsf_alignment", 0),
                sub_scores.get("financial_integrity", 0),
                sub_scores.get("lease_leverage", 0),
                sub_scores.get("risk_profile", 0),
                sub_scores.get("document_coverage_bonus", 0),
            ])
            
            old_overall = synthesis["deal_score"].get("overall_score", 0)
            synthesis["deal_score"]["overall_score"] = min(new_overall, 100)
            
            # Update tier based on new score
            if new_overall >= 80:
                synthesis["deal_score"]["tier"] = "GREEN"
                synthesis["deal_score"]["deal_readiness"] = "Proceed with confidence"
            elif new_overall >= 60:
                synthesis["deal_score"]["tier"] = "YELLOW"
                synthesis["deal_score"]["deal_readiness"] = "Proceed with conditions"
            elif new_overall >= 40:
                synthesis["deal_score"]["tier"] = "ORANGE"
                synthesis["deal_score"]["deal_readiness"] = "Material gaps exist"
            else:
                synthesis["deal_score"]["tier"] = "RED"
                synthesis["deal_score"]["deal_readiness"] = "Insufficient data"
            
            print(f"[SCORING] Adjusted: data_completeness {old_score}->{data_completeness}, overall {old_overall}->{new_overall}")
            score_summary = synthesis["deal_score"]
        
        # Add doc_types_present to synthesis for frontend
        synthesis["doc_types_present"] = doc_types
        synthesis["categories_found"] = categories_found
        
        return {"synthesis": synthesis, "rsf_recovery": result.get("rsf_recovery", {}),
                "score_summary": score_summary,
                "synthesis_error": None, "pipeline_stage": "synthesized"}
    except Exception as e:
        return {"synthesis": {}, "rsf_recovery": {}, "score_summary": {},
                "synthesis_error": str(e), "pipeline_stage": "synthesis_failed",
                "pipeline_errors": [f"Synthesis failed: {str(e)}"]}


def verify_arithmetic(state: CREPipelineState) -> dict:
    by_type: dict = {}
    for ext in state["extractions"]:
        t = ext["doc_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(ext)
    verification = _arithmetic.verify_arithmetic(
        synthesis=state.get("synthesis", {}), extractions=by_type)
    return {"arithmetic_verification": verification, "pipeline_stage": "verified"}


async def enrich_with_gen1_agents(state: CREPipelineState) -> dict:
    by_type: dict = {}
    for ext in state["extractions"]:
        t = ext["doc_type"]
        if t not in by_type:
            by_type[t] = []
        by_type[t].append(ext)

    lease_abstracts = [e["extraction"] for e in by_type.get("LEASE", []) if e.get("extraction")]
    rent_roll_data = by_type["RENT_ROLL"][0].get("extraction", {}) if "RENT_ROLL" in by_type and by_type["RENT_ROLL"] else {}
    boma_data = {"data": by_type["BOMA"][0].get("extraction", {})} if "BOMA" in by_type and by_type["BOMA"] else None
    doc_list = [{"type": d["doc_type"], "filename": d["filename"]} for d in state["classified_documents"]]

    rsf_result, red_flag_result, completeness_result = await asyncio.gather(
        _rsf_agent.reconcile(rent_roll_data=rent_roll_data, lease_data=lease_abstracts, boma_data=boma_data),
        _red_flag_agent.detect_flags(rent_roll_analysis=rent_roll_data, lease_abstracts=lease_abstracts, rsf_reconciliation={}),
        _classifier.assess_completeness(doc_list),
        return_exceptions=True,
    )

    def safe(r, fallback=None):
        return fallback if isinstance(r, Exception) else r

    rsf_rec = safe(rsf_result, {})
    red_flags = safe(red_flag_result, {"red_flags": []})
    completeness = safe(completeness_result, {})

    try:
        deal_score = await _risk_agent.score_deal(
            documents_status=completeness, rsf_reconciliation=rsf_rec,
            lease_abstracts=lease_abstracts, rent_roll_analysis=rent_roll_data,
            red_flags=red_flags.get("red_flags", []))
    except Exception as e:
        deal_score = {"error": str(e)}

    errors = [f"{k} failed: {v}" for k, v in {
        "RSF": rsf_result, "RedFlags": red_flag_result, "Completeness": completeness_result
    }.items() if isinstance(v, Exception)]

    return {"rsf_reconciliation": rsf_rec, "red_flags_result": red_flags,
            "deal_score_result": deal_score, "completeness_result": completeness,
            "pipeline_stage": "enriched", "pipeline_errors": errors,
            "completed_at": datetime.now(timezone.utc).isoformat()}


def should_enrich(state: CREPipelineState) -> str:
    return "skip" if (state.get("synthesis_error") and not state.get("synthesis")) else "enrich"


def skip_enrichment(state: CREPipelineState) -> dict:
    return {"pipeline_stage": "completed_with_errors",
            "completed_at": datetime.now(timezone.utc).isoformat()}


def build_graph() -> StateGraph:
    builder = StateGraph(CREPipelineState)
    builder.add_node("ingest_documents", ingest_documents)
    builder.add_node("classify_documents", classify_documents)
    builder.add_node("extract_single_document", extract_single_document)
    builder.add_node("synthesize", synthesize)
    builder.add_node("verify_arithmetic", verify_arithmetic)
    builder.add_node("enrich_with_gen1_agents", enrich_with_gen1_agents)
    builder.add_node("skip_enrichment", skip_enrichment)
    builder.add_edge(START, "ingest_documents")
    builder.add_edge("ingest_documents", "classify_documents")
    builder.add_conditional_edges("classify_documents", fan_out_extractions)
    builder.add_edge("extract_single_document", "synthesize")
    builder.add_edge("synthesize", "verify_arithmetic")
    builder.add_conditional_edges("verify_arithmetic", should_enrich,
                                   {"enrich": "enrich_with_gen1_agents", "skip": "skip_enrichment"})
    builder.add_edge("enrich_with_gen1_agents", END)
    builder.add_edge("skip_enrichment", END)
    return builder.compile()


graph = build_graph()
