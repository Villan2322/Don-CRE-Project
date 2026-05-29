from pydantic import BaseModel, Field
from typing import Optional
from datetime import date
from enum import Enum


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class DocumentType(str, Enum):
    LEASE = "lease"
    RENT_ROLL = "rent_roll"
    BOMA_MEASUREMENT = "boma_measurement"
    OPERATING_STATEMENT = "operating_statement"
    AR_AGING = "ar_aging"
    CAM_RECONCILIATION = "cam_reconciliation"
    ESTOPPEL = "estoppel"
    OTHER = "other"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentUpload(BaseModel):
    filename: str
    document_type: Optional[DocumentType] = None
    content_type: str


class ProcessedDocument(BaseModel):
    id: str
    filename: str
    document_type: DocumentType
    status: ProcessingStatus
    uploaded_at: str
    processed_at: Optional[str] = None
    page_count: Optional[int] = None
    extracted_data: Optional[dict] = None


class LeaseAbstract(BaseModel):
    lease_id: str
    tenant_name: str
    suite: str
    rsf: float
    lease_start: date
    lease_end: date
    base_rent_psf: float
    annual_base_rent: float
    rent_escalation: Optional[str] = None
    expense_structure: Optional[str] = None
    renewal_options: Optional[str] = None
    termination_rights: Optional[str] = None
    tenant_improvements: Optional[float] = None
    free_rent_months: Optional[int] = None
    security_deposit: Optional[float] = None
    guarantor: Optional[str] = None
    permitted_use: Optional[str] = None
    exclusivity_clause: Optional[str] = None
    co_tenancy: Optional[str] = None
    assignment_subletting: Optional[str] = None
    source_document: str
    extraction_confidence: float = Field(ge=0, le=1)
    missing_fields: list[str] = []


class TenantRecord(BaseModel):
    tenant_id: str
    tenant_name: str
    suite: str
    rsf_rent_roll: float
    rsf_lease: Optional[float] = None
    rsf_boma: Optional[float] = None
    rsf_variance: Optional[float] = None
    monthly_rent: float
    annual_rent: float
    rent_psf: float
    lease_start: date
    lease_end: date
    days_to_expiry: int
    has_renewal_option: bool = False
    ar_current: float = 0
    ar_30_days: float = 0
    ar_60_days: float = 0
    ar_90_plus: float = 0
    risk_level: Severity = Severity.LOW


class RSFReconciliation(BaseModel):
    total_rsf_rent_roll: float
    total_rsf_leases: float
    total_rsf_boma: float
    variance_rent_roll_vs_boma: float
    variance_percentage: float
    estimated_annual_revenue_impact: float
    discrepancies: list[dict]


class RedFlag(BaseModel):
    id: str
    category: str
    severity: Severity
    title: str
    description: str
    affected_tenants: list[str] = []
    financial_impact: Optional[float] = None
    recommended_action: str
    source_documents: list[str] = []


class DealScore(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    tier: str
    sub_scores: dict[str, int]
    score_factors: list[dict]


class AnalysisResult(BaseModel):
    deal_id: str
    property_name: str
    property_address: str
    analysis_date: str
    deal_score: DealScore
    rsf_reconciliation: RSFReconciliation
    tenants: list[TenantRecord]
    lease_abstracts: list[LeaseAbstract]
    red_flags: list[RedFlag]
    documents_processed: list[ProcessedDocument]
    what_to_get_next: list[str]
    financial_summary: dict


class UploadResponse(BaseModel):
    message: str
    document_id: str
    status: ProcessingStatus
    document_type: Optional[str] = None


class AnalysisRequest(BaseModel):
    deal_id: str
    documents: list[str]


class AnalysisResponse(BaseModel):
    deal_id: str
    status: ProcessingStatus
    message: str
    result: Optional[AnalysisResult] = None
