import operator
from typing import Annotated, Optional
from typing_extensions import TypedDict


class CREPipelineState(TypedDict, total=False):
    deal_id: str
    deal_name: str
    as_of: Optional[str]                       # ISO date the metrics are measured from
    raw_files: dict[str, bytes]
    file_content_types: dict[str, str]
    raw_documents: Annotated[list[dict], operator.add]
    ingest_errors: Annotated[list[str], operator.add]
    classified_documents: Annotated[list[dict], operator.add]
    extractions: Annotated[list[dict], operator.add]
    metrics: dict
    synthesis: dict
    report: dict
    pipeline_stage: str
    pipeline_errors: Annotated[list[str], operator.add]
    completed_at: Optional[str]


class SingleDocumentState(TypedDict):
    doc_id: str
    deal_name: str
    filename: str
    doc_type: str
    extracted_text: str


def initial_state(deal_id: str, deal_name: str, raw_files: dict[str, bytes],
                  content_types: dict[str, str], as_of: Optional[str] = None) -> CREPipelineState:
    return {
        "deal_id": deal_id, "deal_name": deal_name, "as_of": as_of,
        "raw_files": raw_files, "file_content_types": content_types,
        "raw_documents": [], "ingest_errors": [], "classified_documents": [],
        "extractions": [], "metrics": {}, "synthesis": {}, "report": {},
        "pipeline_stage": "pending", "pipeline_errors": [], "completed_at": None,
    }
