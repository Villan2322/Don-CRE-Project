import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict


class RawDocument(TypedDict):
    doc_id: str
    deal_name: str
    filename: str
    content_type: str
    file_type: str
    extracted_text: str
    page_count: Optional[int]
    needs_ocr: bool
    ocr_performed: bool
    ocr_confidence: Optional[float]
    is_parseable: bool
    parse_method: str
    parse_reason: str


class ClassifiedDocument(TypedDict):
    doc_id: str
    deal_name: str
    filename: str
    file_type: str
    extracted_text: str
    page_count: Optional[int]
    ocr_performed: bool
    doc_type: str
    classification_confidence: float
    classification_reasoning: str


class ExtractionResult(TypedDict):
    doc_id: str
    deal_name: str
    filename: str
    doc_type: str
    extraction: dict
    parse_error: Optional[str]
    pipeline_stage: str
    extraction_timestamp: str
    enriched: Optional[dict]
    missing_fields: list[str]
    abstract_complete: bool


class CREPipelineState(TypedDict):
    deal_id: str
    deal_name: str
    raw_files: dict[str, bytes]
    file_content_types: dict[str, str]
    raw_documents: Annotated[list[RawDocument], operator.add]
    ingest_errors: Annotated[list[str], operator.add]
    classified_documents: Annotated[list[ClassifiedDocument], operator.add]
    classification_errors: Annotated[list[str], operator.add]
    extractions: Annotated[list[ExtractionResult], operator.add]
    extraction_errors: Annotated[list[str], operator.add]
    synthesis: dict
    rsf_recovery: dict
    score_summary: dict
    synthesis_error: Optional[str]
    arithmetic_verification: dict
    rent_roll_analysis: dict
    rsf_reconciliation: dict
    red_flags_result: dict
    deal_score_result: dict
    completeness_result: dict
    pipeline_stage: str
    pipeline_errors: Annotated[list[str], operator.add]
    completed_at: Optional[str]


class SingleDocumentState(TypedDict):
    doc_id: str
    deal_name: str
    filename: str
    doc_type: str
    extracted_text: str
    ocr_performed: bool
    classification_confidence: float
