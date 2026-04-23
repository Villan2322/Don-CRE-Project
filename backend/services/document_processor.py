import io
from typing import Optional
from datetime import datetime
import uuid

# PDF and Excel processing
try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import pandas as pd
except ImportError:
    pd = None

from ..agents import (
    DocumentClassifierAgent,
    LeaseAbstractionAgent,
    RentRollAgent,
    RSFReconciliationAgent,
    RiskScoringAgent,
    RedFlagDetectionAgent,
)
from ..models.schemas import (
    DocumentType,
    ProcessingStatus,
    ProcessedDocument,
    AnalysisResult,
)


class DocumentProcessor:
    """Orchestrates document processing and AI agent analysis."""
    
    def __init__(self):
        self.classifier = DocumentClassifierAgent()
        self.lease_agent = LeaseAbstractionAgent()
        self.rent_roll_agent = RentRollAgent()
        self.rsf_agent = RSFReconciliationAgent()
        self.risk_agent = RiskScoringAgent()
        self.red_flag_agent = RedFlagDetectionAgent()
        
        # In-memory storage (use database in production)
        self.documents: dict[str, ProcessedDocument] = {}
        self.deals: dict[str, dict] = {}
    
    def extract_text_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF file."""
        if PdfReader is None:
            return "[PDF parsing not available - PyPDF2 not installed]"
        
        try:
            pdf_file = io.BytesIO(file_content)
            reader = PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text() or ""
            return text
        except Exception as e:
            return f"[Error extracting PDF text: {str(e)}]"
    
    def extract_data_from_excel(self, file_content: bytes) -> str:
        """Extract data from Excel file as text representation."""
        if openpyxl is None or pd is None:
            return "[Excel parsing not available - openpyxl/pandas not installed]"
        
        try:
            excel_file = io.BytesIO(file_content)
            workbook = openpyxl.load_workbook(excel_file, data_only=True)
            
            all_sheets_text = []
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                sheet_text = f"=== Sheet: {sheet_name} ===\n"
                
                for row in sheet.iter_rows(values_only=True):
                    row_text = "\t".join(str(cell) if cell is not None else "" for cell in row)
                    sheet_text += row_text + "\n"
                
                all_sheets_text.append(sheet_text)
            
            return "\n\n".join(all_sheets_text)
        except Exception as e:
            return f"[Error extracting Excel data: {str(e)}]"
    
    async def process_document(
        self, 
        filename: str, 
        file_content: bytes,
        content_type: str
    ) -> ProcessedDocument:
        """Process an uploaded document."""
        doc_id = str(uuid.uuid4())
        
        # Extract text based on file type
        if content_type == "application/pdf" or filename.endswith(".pdf"):
            extracted_text = self.extract_text_from_pdf(file_content)
            page_count = len(PdfReader(io.BytesIO(file_content)).pages) if PdfReader else None
        elif content_type in [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
        ] or filename.endswith((".xlsx", ".xls")):
            extracted_text = self.extract_data_from_excel(file_content)
            page_count = None
        else:
            extracted_text = file_content.decode("utf-8", errors="ignore")
            page_count = None
        
        # Classify document
        classification = await self.classifier.classify_document(extracted_text, filename)
        
        doc_type = DocumentType.OTHER
        if "classification" in classification:
            type_str = classification["classification"].get("document_type", "OTHER")
            try:
                doc_type = DocumentType(type_str.lower())
            except ValueError:
                doc_type = DocumentType.OTHER
        
        # Create document record
        doc = ProcessedDocument(
            id=doc_id,
            filename=filename,
            document_type=doc_type,
            status=ProcessingStatus.COMPLETED,
            uploaded_at=datetime.utcnow().isoformat(),
            processed_at=datetime.utcnow().isoformat(),
            page_count=page_count,
            extracted_data={
                "text_preview": extracted_text[:1000],
                "classification": classification,
                "full_text": extracted_text,
            }
        )
        
        self.documents[doc_id] = doc
        return doc
    
    async def run_full_analysis(self, deal_id: str, document_ids: list[str]) -> AnalysisResult:
        """Run full analysis pipeline on a set of documents."""
        
        # Gather documents
        docs = [self.documents[doc_id] for doc_id in document_ids if doc_id in self.documents]
        
        # Separate by type
        leases = [d for d in docs if d.document_type == DocumentType.LEASE]
        rent_rolls = [d for d in docs if d.document_type == DocumentType.RENT_ROLL]
        boma_reports = [d for d in docs if d.document_type == DocumentType.BOMA_MEASUREMENT]
        
        # Extract lease abstracts
        lease_abstracts = []
        for lease_doc in leases:
            if lease_doc.extracted_data and "full_text" in lease_doc.extracted_data:
                result = await self.lease_agent.extract_lease(
                    lease_doc.extracted_data["full_text"]
                )
                if "lease_abstract" in result:
                    lease_abstracts.append(result["lease_abstract"])
        
        # Parse rent roll
        rent_roll_analysis = {}
        for rr_doc in rent_rolls:
            if rr_doc.extracted_data and "full_text" in rr_doc.extracted_data:
                rent_roll_analysis = await self.rent_roll_agent.parse_rent_roll(
                    rr_doc.extracted_data["full_text"]
                )
                break  # Use first rent roll
        
        # RSF reconciliation
        boma_data = None
        for boma_doc in boma_reports:
            if boma_doc.extracted_data and "full_text" in boma_doc.extracted_data:
                boma_data = {"text": boma_doc.extracted_data["full_text"]}
                break
        
        rsf_reconciliation = await self.rsf_agent.reconcile(
            rent_roll_data=rent_roll_analysis,
            lease_data=lease_abstracts,
            boma_data=boma_data
        )
        
        # Red flag detection
        red_flags_result = await self.red_flag_agent.detect_flags(
            rent_roll_analysis=rent_roll_analysis,
            lease_abstracts=lease_abstracts,
            rsf_reconciliation=rsf_reconciliation
        )
        
        # Document completeness
        completeness = await self.classifier.assess_completeness(
            [{"type": d.document_type.value, "filename": d.filename} for d in docs]
        )
        
        # Risk scoring
        deal_score = await self.risk_agent.score_deal(
            documents_status=completeness,
            rsf_reconciliation=rsf_reconciliation,
            lease_abstracts=lease_abstracts,
            rent_roll_analysis=rent_roll_analysis,
            red_flags=red_flags_result.get("red_flags", [])
        )
        
        # Build result
        from ..models.schemas import DealScore, RSFReconciliation, RedFlag, TenantRecord, LeaseAbstract, Severity

        # --- Map tenants from rent roll ---
        tenant_records: list[TenantRecord] = []
        for t in rent_roll_analysis.get("tenants", []):
            try:
                # Calculate days to expiry
                from datetime import date as date_type
                lease_end_str = t.get("lease_end") or t.get("expiry_date") or ""
                try:
                    lease_end_date = date_type.fromisoformat(str(lease_end_str)[:10])
                    days_to_expiry = max((lease_end_date - date_type.today()).days, 0)
                except Exception:
                    lease_end_date = date_type(2025, 12, 31)
                    days_to_expiry = 0

                lease_start_str = t.get("lease_start") or t.get("commencement_date") or ""
                try:
                    lease_start_date = date_type.fromisoformat(str(lease_start_str)[:10])
                except Exception:
                    lease_start_date = date_type(2020, 1, 1)

                monthly_rent = float(t.get("monthly_rent", 0) or 0)
                annual_rent = float(t.get("annual_rent", monthly_rent * 12) or 0)
                rsf = float(t.get("rsf", 1) or 1)
                rent_psf = float(t.get("rent_psf", annual_rent / rsf if rsf else 0) or 0)

                tenant_records.append(TenantRecord(
                    tenant_id=str(uuid.uuid4()),
                    tenant_name=str(t.get("tenant_name", "Unknown")),
                    suite=str(t.get("suite", "")),
                    rsf_rent_roll=rsf,
                    monthly_rent=monthly_rent,
                    annual_rent=annual_rent,
                    rent_psf=rent_psf,
                    lease_start=lease_start_date,
                    lease_end=lease_end_date,
                    days_to_expiry=days_to_expiry,
                    has_renewal_option=bool(t.get("renewal_option", False)),
                    risk_level=Severity.LOW,
                ))
            except Exception:
                continue

        # --- Map lease abstracts ---
        lease_abstract_records: list[LeaseAbstract] = []
        for idx, la in enumerate(lease_abstracts):
            try:
                from datetime import date as date_type
                ls_str = la.get("lease_start") or ""
                le_str = la.get("lease_end") or ""
                try:
                    ls_date = date_type.fromisoformat(str(ls_str)[:10])
                except Exception:
                    ls_date = date_type(2020, 1, 1)
                try:
                    le_date = date_type.fromisoformat(str(le_str)[:10])
                except Exception:
                    le_date = date_type(2025, 12, 31)

                lease_abstract_records.append(LeaseAbstract(
                    lease_id=f"LA-{idx+1:03d}",
                    tenant_name=str(la.get("tenant_name", "Unknown")),
                    suite=str(la.get("suite", "")),
                    rsf=float(la.get("rsf", 0) or 0),
                    lease_start=ls_date,
                    lease_end=le_date,
                    base_rent_psf=float(la.get("base_rent_psf", 0) or 0),
                    annual_base_rent=float(la.get("annual_base_rent", 0) or 0),
                    rent_escalation=la.get("rent_escalation"),
                    expense_structure=la.get("expense_structure"),
                    renewal_options=la.get("renewal_options"),
                    termination_rights=la.get("termination_rights"),
                    tenant_improvements=la.get("tenant_improvements"),
                    free_rent_months=la.get("free_rent_months"),
                    security_deposit=la.get("security_deposit"),
                    guarantor=la.get("guarantor"),
                    permitted_use=la.get("permitted_use"),
                    exclusivity_clause=la.get("exclusivity_clause"),
                    co_tenancy=la.get("co_tenancy"),
                    assignment_subletting=la.get("assignment_subletting"),
                    source_document=f"lease_{idx+1}.pdf",
                    extraction_confidence=float(la.get("extraction_confidence", 0.8) or 0.8),
                    missing_fields=list(la.get("missing_fields", [])),
                ))
            except Exception:
                continue

        # --- Map red flags ---
        red_flag_records: list[RedFlag] = []
        raw_flags = red_flags_result.get("red_flags", [])
        for rf in raw_flags:
            try:
                sev_str = str(rf.get("severity", "medium")).lower()
                sev = Severity(sev_str) if sev_str in [s.value for s in Severity] else Severity.MEDIUM
                red_flag_records.append(RedFlag(
                    id=str(rf.get("id", str(uuid.uuid4()))),
                    category=str(rf.get("category", "general")),
                    severity=sev,
                    title=str(rf.get("title", "")),
                    description=str(rf.get("description", "")),
                    affected_tenants=list(rf.get("affected_tenants", [])),
                    financial_impact=rf.get("financial_impact"),
                    recommended_action=str(rf.get("recommended_action", "")),
                    source_documents=list(rf.get("source_documents", [])),
                ))
            except Exception:
                continue

        result = AnalysisResult(
            deal_id=deal_id,
            property_name="Property Under Analysis",
            property_address="Address TBD",
            analysis_date=datetime.utcnow().isoformat(),
            deal_score=DealScore(
                overall_score=int(deal_score.get("deal_score", {}).get("overall_score", 75)),
                tier=str(deal_score.get("deal_score", {}).get("tier", "Standard")),
                sub_scores={k: int(v) for k, v in deal_score.get("deal_score", {}).get("sub_scores", {}).items()},
                score_factors=list(deal_score.get("score_factors", []))
            ),
            rsf_reconciliation=RSFReconciliation(
                total_rsf_rent_roll=float(rsf_reconciliation.get("reconciliation", {}).get("total_rsf_rent_roll", 0) or 0),
                total_rsf_leases=float(rsf_reconciliation.get("reconciliation", {}).get("total_rsf_leases", 0) or 0),
                total_rsf_boma=float(rsf_reconciliation.get("reconciliation", {}).get("total_rsf_boma", 0) or 0),
                variance_rent_roll_vs_boma=float(rsf_reconciliation.get("reconciliation", {}).get("variance_rent_roll_vs_boma", 0) or 0),
                variance_percentage=float(rsf_reconciliation.get("reconciliation", {}).get("variance_percentage", 0) or 0),
                estimated_annual_revenue_impact=float(rsf_reconciliation.get("reconciliation", {}).get("estimated_annual_revenue_impact", 0) or 0),
                discrepancies=list(rsf_reconciliation.get("by_tenant", []))
            ),
            tenants=tenant_records,
            lease_abstracts=lease_abstract_records,
            red_flags=red_flag_records,
            documents_processed=docs,
            what_to_get_next=list(completeness.get("what_to_request_next", [])),
            financial_summary=rent_roll_analysis.get("summary", {})
        )
        
        self.deals[deal_id] = {"result": result, "raw_data": {
            "lease_abstracts": lease_abstracts,
            "rent_roll": rent_roll_analysis,
            "rsf": rsf_reconciliation,
            "red_flags": red_flags_result,
            "score": deal_score
        }}
        
        return result


# Singleton instance
processor = DocumentProcessor()
