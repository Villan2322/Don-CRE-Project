from typing import Optional
from datetime import datetime
import uuid

from agents import (
    DocumentParsingAgent,
    OCRAgent,
    DocumentClassifierAgent,
    LeaseAbstractionAgent,
    RentRollAgent,
    RSFReconciliationAgent,
    RiskScoringAgent,
    RedFlagDetectionAgent,
)
from models.schemas import (
    DocumentType,
    ProcessingStatus,
    ProcessedDocument,
    AnalysisResult,
)


class DocumentProcessor:
    """
    Orchestrates the full document processing pipeline:

      1. DocumentParsingAgent  — detects file type; extracts text if text-native,
                                 or flags as needing OCR if scanned/image-based
      2. OCRAgent              — fires only for scanned PDFs; renders pages to
                                 images, runs Tesseract, then LLM-cleans the output
      3. DocumentClassifierAgent — classifies the now-readable text by CRE doc type
      4. Downstream agents     — lease abstraction, rent roll, RSF reconciliation,
                                 red flag detection, risk scoring
    """

    def __init__(self):
        # Stage 1 & 2 — parsing and OCR
        self.parsing_agent = DocumentParsingAgent()
        self.ocr_agent = OCRAgent()

        # Stage 3 — classification
        self.classifier = DocumentClassifierAgent()

        # Stage 4 — downstream analysis
        self.lease_agent = LeaseAbstractionAgent()
        self.rent_roll_agent = RentRollAgent()
        self.rsf_agent = RSFReconciliationAgent()
        self.risk_agent = RiskScoringAgent()
        self.red_flag_agent = RedFlagDetectionAgent()

        # In-memory storage (replace with a database in production)
        self.documents: dict[str, ProcessedDocument] = {}
        self.deals: dict[str, dict] = {}

    async def process_document(
        self,
        filename: str,
        file_content: bytes,
        content_type: str,
    ) -> ProcessedDocument:
        """
        Full ingestion pipeline for a single uploaded document.

        Steps:
          1. ParseabilityCheck  → text or scanned?
          2. OCR (if scanned)   → raw OCR + LLM cleanup
          3. Classify           → CRE document type
          4. Store              → return ProcessedDocument record
        """
        doc_id = str(uuid.uuid4())

        # ── Stage 1: Parseability check ───────────────────────────────────────
        parse_result = self.parsing_agent.check(
            filename=filename,
            file_content=file_content,
            content_type=content_type,
        )

        ocr_metadata: Optional[dict] = None
        extracted_text = ""

        if not parse_result.is_parseable:
            # Cannot process this file at all
            doc = ProcessedDocument(
                id=doc_id,
                filename=filename,
                document_type=DocumentType.OTHER,
                status=ProcessingStatus.FAILED,
                uploaded_at=datetime.utcnow().isoformat(),
                processed_at=datetime.utcnow().isoformat(),
                page_count=parse_result.page_count,
                extracted_data={
                    "parse_check": parse_result.to_dict(),
                    "error": parse_result.reason,
                },
            )
            self.documents[doc_id] = doc
            return doc

        # ── Stage 2: OCR (scanned PDFs only) ─────────────────────────────────
        if parse_result.needs_ocr:
            ocr_result = await self.ocr_agent.process(
                file_content=file_content,
                filename=filename,
                page_count=parse_result.page_count,
            )
            ocr_metadata = ocr_result
            extracted_text = ocr_result.get("cleaned_text", "")

            # If OCR also failed to produce readable text, mark as failed
            if not extracted_text.strip() or not ocr_result.get("document_readable", False):
                doc = ProcessedDocument(
                    id=doc_id,
                    filename=filename,
                    document_type=DocumentType.OTHER,
                    status=ProcessingStatus.FAILED,
                    uploaded_at=datetime.utcnow().isoformat(),
                    processed_at=datetime.utcnow().isoformat(),
                    page_count=parse_result.page_count,
                    extracted_data={
                        "parse_check": parse_result.to_dict(),
                        "ocr": ocr_metadata,
                        "error": "OCR could not produce readable text from this document",
                    },
                )
                self.documents[doc_id] = doc
                return doc
        else:
            # Text-native document — use directly
            extracted_text = parse_result.extracted_text

        # ── Stage 3: Classification ───────────────────────────────────────────
        classification = await self.classifier.classify_document(
            extracted_text, filename
        )

        doc_type = DocumentType.OTHER
        if "classification" in classification:
            type_str = classification["classification"].get("document_type", "OTHER")
            try:
                doc_type = DocumentType(type_str.lower())
            except ValueError:
                doc_type = DocumentType.OTHER

        # ── Build and store document record ───────────────────────────────────
        doc = ProcessedDocument(
            id=doc_id,
            filename=filename,
            document_type=doc_type,
            status=ProcessingStatus.COMPLETED,
            uploaded_at=datetime.utcnow().isoformat(),
            processed_at=datetime.utcnow().isoformat(),
            page_count=parse_result.page_count,
            extracted_data={
                "parse_check": parse_result.to_dict(),
                "ocr": ocr_metadata,
                "classification": classification,
                "text_preview": extracted_text[:1000],
                "full_text": extracted_text,
            },
        )

        self.documents[doc_id] = doc
        return doc

    async def run_full_analysis(
        self, deal_id: str, document_ids: list[str]
    ) -> AnalysisResult:
        """
        Run the full analysis pipeline on a set of already-processed documents.

        Only documents with status=COMPLETED are included in analysis.
        """
        docs = [
            self.documents[did]
            for did in document_ids
            if did in self.documents and self.documents[did].status == ProcessingStatus.COMPLETED
        ]

        leases = [d for d in docs if d.document_type == DocumentType.LEASE]
        rent_rolls = [d for d in docs if d.document_type == DocumentType.RENT_ROLL]
        boma_reports = [d for d in docs if d.document_type == DocumentType.BOMA_MEASUREMENT]

        # Lease abstraction
        lease_abstracts = []
        for lease_doc in leases:
            if lease_doc.extracted_data and "full_text" in lease_doc.extracted_data:
                result = await self.lease_agent.extract_lease(
                    lease_doc.extracted_data["full_text"]
                )
                if "lease_abstract" in result:
                    lease_abstracts.append(result["lease_abstract"])

        # Rent roll parsing
        rent_roll_analysis = {}
        for rr_doc in rent_rolls:
            if rr_doc.extracted_data and "full_text" in rr_doc.extracted_data:
                rent_roll_analysis = await self.rent_roll_agent.parse_rent_roll(
                    rr_doc.extracted_data["full_text"]
                )
                break

        # RSF reconciliation
        boma_data = None
        for boma_doc in boma_reports:
            if boma_doc.extracted_data and "full_text" in boma_doc.extracted_data:
                boma_data = {"text": boma_doc.extracted_data["full_text"]}
                break

        rsf_reconciliation = await self.rsf_agent.reconcile(
            rent_roll_data=rent_roll_analysis,
            lease_data=lease_abstracts,
            boma_data=boma_data,
        )

        # Red flag detection
        red_flags_result = await self.red_flag_agent.detect_flags(
            rent_roll_analysis=rent_roll_analysis,
            lease_abstracts=lease_abstracts,
            rsf_reconciliation=rsf_reconciliation,
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
            red_flags=red_flags_result.get("red_flags", []),
        )

        from models.schemas import DealScore, RSFReconciliation

        result = AnalysisResult(
            deal_id=deal_id,
            property_name="Property Under Analysis",
            property_address="Address TBD",
            analysis_date=datetime.utcnow().isoformat(),
            deal_score=DealScore(
                overall_score=deal_score.get("deal_score", {}).get("overall_score", 75),
                tier=deal_score.get("deal_score", {}).get("tier", "Standard"),
                sub_scores=deal_score.get("deal_score", {}).get("sub_scores", {}),
                score_factors=deal_score.get("score_factors", []),
            ),
            rsf_reconciliation=RSFReconciliation(
                total_rsf_rent_roll=rsf_reconciliation.get("reconciliation", {}).get("total_rsf_rent_roll", 0),
                total_rsf_leases=rsf_reconciliation.get("reconciliation", {}).get("total_rsf_leases", 0),
                total_rsf_boma=rsf_reconciliation.get("reconciliation", {}).get("total_rsf_boma", 0),
                variance_rent_roll_vs_boma=rsf_reconciliation.get("reconciliation", {}).get("variance_rent_roll_vs_boma", 0),
                variance_percentage=rsf_reconciliation.get("reconciliation", {}).get("variance_percentage", 0),
                estimated_annual_revenue_impact=rsf_reconciliation.get("reconciliation", {}).get("estimated_annual_revenue_impact", 0),
                discrepancies=rsf_reconciliation.get("by_tenant", []),
            ),
            tenants=[],
            lease_abstracts=[],
            red_flags=[],
            documents_processed=docs,
            what_to_get_next=completeness.get("what_to_request_next", []),
            financial_summary=rent_roll_analysis.get("summary", {}),
        )

        self.deals[deal_id] = {
            "result": result,
            "raw_data": {
                "lease_abstracts": lease_abstracts,
                "rent_roll": rent_roll_analysis,
                "rsf": rsf_reconciliation,
                "red_flags": red_flags_result,
                "score": deal_score,
            },
        }

        return result


# Singleton instance
processor = DocumentProcessor()
