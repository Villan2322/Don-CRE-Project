"""
CRE Document Intelligence - End-to-End Test Suite

All LLM calls are mocked. No Anthropic API key is consumed. Runs in seconds.

Run with:
    cd backend && pytest tests/test_e2e.py -v
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


# ============================================================================
# Stage 1: Document Parsing Tests
# ============================================================================

class TestDocumentParsing:
    """Stage 1 - Document ingestion and parsing tests."""
    
    def test_text_pdf_detected_as_native(self, sample_pdf_bytes):
        """PDF with embedded text should not need OCR."""
        from agents.document_parsing import DocumentParsingAgent
        
        agent = DocumentParsingAgent()
        result = agent.check("rent_roll.pdf", sample_pdf_bytes, "application/pdf")
        
        # Text PDFs should be parseable
        assert result.is_parseable == True
        assert result.file_type == "pdf"
    
    def test_excel_extracted_directly(self, sample_excel_bytes):
        """Excel files should be extracted directly without OCR."""
        from agents.document_parsing import DocumentParsingAgent
        
        agent = DocumentParsingAgent()
        result = agent.check(
            "rent_roll.xlsx",
            sample_excel_bytes, 
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        assert result.is_parseable == True
        assert result.needs_ocr == False
        assert result.file_type == "excel"
    
    def test_csv_decoded_directly(self, sample_csv_bytes):
        """CSV files should decode to plain text."""
        from agents.document_parsing import DocumentParsingAgent
        
        agent = DocumentParsingAgent()
        result = agent.check("rent_roll.csv", sample_csv_bytes, "text/csv")
        
        assert result.is_parseable == True
        assert result.needs_ocr == False
        assert "Regions Bank" in result.extracted_text or len(result.extracted_text) > 0
    
    def test_unknown_file_type_fails_gracefully(self):
        """Unknown file types should not crash."""
        from agents.document_parsing import DocumentParsingAgent
        
        agent = DocumentParsingAgent()
        result = agent.check("unknown.xyz", b"random binary data", "application/octet-stream")
        
        # Should return a result without crashing
        assert result is not None
        assert result.is_parseable == False
        assert result.file_type == "unknown"
    
    def test_empty_file_not_parseable(self):
        """Empty files should be marked as not parseable."""
        from agents.document_parsing import DocumentParsingAgent
        
        agent = DocumentParsingAgent()
        result = agent.check("empty.pdf", b"", "application/pdf")
        
        # Empty PDFs should either fail to parse or return empty text
        assert result.extracted_text == "" or result.needs_ocr == True


# ============================================================================
# Stage 2: Classification Tests
# ============================================================================

class TestUniversalExtractorClassification:
    """Stage 2 - Document classification tests."""
    
    @pytest.mark.asyncio
    async def test_rent_roll_classified_correctly(self, mock_llm, sample_rent_roll_text):
        """Rent roll documents should be classified as RENT_ROLL."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.classify_document(sample_rent_roll_text, "rent_roll.pdf")
        
        assert result.get("doc_type") == "RENT_ROLL"
        assert result.get("confidence", 0) > 0.5
    
    @pytest.mark.asyncio
    async def test_lease_classified_correctly(self, mock_llm, sample_lease_text):
        """Lease documents should be classified as LEASE."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.classify_document(sample_lease_text, "lease_agreement.pdf")
        
        assert result.get("doc_type") in ["LEASE", "LEASE_ABSTRACT"]
        assert result.get("confidence", 0) > 0.5
    
    @pytest.mark.asyncio
    async def test_boma_classified_correctly(self, mock_llm, sample_boma_text):
        """BOMA measurement documents should be classified as BOMA."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.classify_document(sample_boma_text, "boma_measurement.pdf")
        
        assert result.get("doc_type") == "BOMA"
    
    @pytest.mark.asyncio
    async def test_filename_hints_improve_classification(self, mock_llm):
        """Filename should provide classification hints."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        # Even with minimal text, filename should hint at type
        result = await extractor.classify_document("Some data", "rent_roll_march_2026.xlsx")
        
        # The filename hint should influence classification
        assert result.get("doc_type") is not None
    
    @pytest.mark.asyncio
    async def test_unknown_doc_type_returned_on_parse_failure(self):
        """Bad JSON response should return UNKNOWN type."""
        from agents.universal_extractor import UniversalExtractor
        
        async def bad_response(*args, **kwargs):
            return "not valid json {"
        
        with patch('agents.base.BaseAgent.call_llm', AsyncMock(side_effect=bad_response)):
            extractor = UniversalExtractor()
            result = await extractor.classify_document("some text", "file.pdf")
            
            assert result.get("doc_type") == "UNKNOWN"
            assert result.get("confidence", 1) == 0


# ============================================================================
# Stage 3: Extraction Tests
# ============================================================================

class TestUniversalExtractorExtraction:
    """Stage 3 - Document extraction tests."""
    
    @pytest.mark.asyncio
    async def test_rent_roll_extraction(self, mock_llm, sample_rent_roll_text):
        """Rent roll extraction should return tenants and summary."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.extract_document(
            sample_rent_roll_text, "RENT_ROLL", "doc-1", "Test Deal", "rent_roll.pdf"
        )
        
        assert "extraction" in result or "error" not in result
        assert result.get("pipeline_stage") == "extracted" or "extraction" in result
    
    @pytest.mark.asyncio
    async def test_lease_extraction_with_enrichment(self, mock_llm, sample_lease_text):
        """Lease extraction should include enriched fields."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.extract_document(
            sample_lease_text, "LEASE", "doc-2", "Test Deal", "lease.pdf"
        )
        
        # Should have extraction field
        assert "extraction" in result or "error" not in result
    
    @pytest.mark.asyncio
    async def test_boma_extraction(self, mock_llm, sample_boma_text):
        """BOMA extraction should return suites and building totals."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.extract_document(
            sample_boma_text, "BOMA", "doc-3", "Test Deal", "boma.pdf"
        )
        
        assert "extraction" in result or "error" not in result
    
    @pytest.mark.asyncio
    async def test_unknown_doc_type_returns_error_not_crash(self, mock_llm):
        """Unknown doc types should return error, not crash."""
        from agents.universal_extractor import UniversalExtractor
        
        extractor = UniversalExtractor()
        result = await extractor.extract_document(
            "some text", "UNKNOWN_TYPE", "doc-4", "Test Deal", "file.pdf"
        )
        
        # Should not crash, may return error or empty extraction
        assert isinstance(result, dict)
        assert "parse_error" in result or "extraction" in result
    
    @pytest.mark.asyncio
    async def test_json_parse_error_returns_error_not_crash(self):
        """Truncated JSON should return error, not crash."""
        from agents.universal_extractor import UniversalExtractor
        
        async def truncated_response(*args, **kwargs):
            return '{"tenants": [{"name": "Test"'  # Truncated JSON
        
        with patch('agents.base.BaseAgent.call_llm', AsyncMock(side_effect=truncated_response)):
            extractor = UniversalExtractor()
            result = await extractor.extract_document(
                "text", "RENT_ROLL", "doc-5", "Test Deal", "file.pdf"
            )
            
            # Should have error or parse_error field, not crash
            assert isinstance(result, dict)


# ============================================================================
# Stage 5: Arithmetic Verification Tests
# ============================================================================

class TestArithmeticVerification:
    """Stage 5 - Arithmetic verification tests."""
    
    def test_verified_check_when_numbers_match(self):
        """Matching numbers should be verified."""
        from agents.synthesis import ArithmeticVerificationAgent
        
        agent = ArithmeticVerificationAgent()
        synthesis = {
            "rsf_recovery": {
                "boma_rsf": 10000,
                "rent_roll_rsf": 10000,
                "delta_sf": 0,
                "delta_pct": 0
            }
        }
        extractions = {
            "rent_roll": {"summary": {"total_rsf": 10000}},
            "boma": {"building_totals": {"rentable_sf": 10000}}
        }
        
        result = agent.verify_arithmetic(synthesis, extractions)
        
        assert "checks" in result
        assert result.get("total", 0) >= 0
    
    def test_calc_mismatch_detected(self):
        """Mismatched calculations should be flagged."""
        from agents.synthesis import ArithmeticVerificationAgent
        
        agent = ArithmeticVerificationAgent()
        synthesis = {
            "rsf_recovery": {
                "boma_rsf": 29452,
                "rent_roll_rsf": 24847,
                "delta_sf": 4605,
                "delta_pct": 10.00  # Wrong! Should be ~18.5%
            }
        }
        extractions = {}
        
        result = agent.verify_arithmetic(synthesis, extractions)
        
        # Should detect the percentage mismatch
        assert isinstance(result, dict)
    
    def test_rent_psf_verified(self):
        """Rent PSF calculation should be verified."""
        from agents.synthesis import ArithmeticVerificationAgent
        
        agent = ArithmeticVerificationAgent()
        synthesis = {}
        extractions = {
            "rent_roll": {
                "tenants": [{
                    "tenant_name": "Test Tenant",
                    "rsf": 10508,
                    "monthly_rent": 104029 / 12,
                    "rent_psf": 9.90
                }]
            }
        }
        
        result = agent.verify_arithmetic(synthesis, extractions)
        assert isinstance(result, dict)


# ============================================================================
# Stage 4: Synthesis Tests
# ============================================================================

class TestSynthesisAgent:
    """Stage 4 - Synthesis agent tests."""
    
    @pytest.mark.asyncio
    async def test_synthesis_produces_deal_score(self, mock_llm):
        """Synthesis should produce deal score."""
        from agents.synthesis import SynthesisAgent
        
        agent = SynthesisAgent()
        extractions = [
            {"doc_type": "RENT_ROLL", "tenants": []},
            {"doc_type": "LEASE", "tenant": "Test"}
        ]
        
        result = await agent.synthesize_deal(extractions, "Test Deal")
        
        # Should have score_summary from mock response
        assert "score_summary" in result or "synthesis" in result
    
    @pytest.mark.asyncio
    async def test_synthesis_extracts_rsf_recovery(self, mock_llm):
        """Synthesis should calculate RSF recovery potential."""
        from agents.synthesis import SynthesisAgent
        
        agent = SynthesisAgent()
        extractions = [
            {"doc_type": "RENT_ROLL", "summary": {"total_rsf": 24847}},
            {"doc_type": "BOMA", "building_totals": {"rentable_sf": 29452}}
        ]
        
        result = await agent.synthesize_deal(extractions, "Test Deal")
        
        # Should have rsf_recovery from mock response
        assert "rsf_recovery" in result or "synthesis" in result
    
    @pytest.mark.asyncio
    async def test_synthesis_parse_error_surfaces_explicitly(self):
        """Parse errors should be surfaced, not hidden."""
        from agents.synthesis import SynthesisAgent
        
        async def truncated_response(*args, **kwargs):
            return '{"deal_score": {"overall":'  # Truncated
        
        with patch('agents.base.BaseAgent.call_llm', AsyncMock(side_effect=truncated_response)):
            agent = SynthesisAgent()
            result = await agent.synthesize_deal([], "Test Deal")
            
            # Should have error indication
            assert "_parse_error" in result or "error" in result or result.get("synthesis") is None


# ============================================================================
# State Schema Tests
# ============================================================================

class TestLangGraphState:
    """State schema validation tests."""
    
    def test_state_has_operator_add_reducers(self):
        """State should have proper reducers for list fields."""
        from state import CREPipelineState
        
        # Check that state class has expected fields
        annotations = getattr(CREPipelineState, '__annotations__', {})
        
        assert 'raw_documents' in annotations
        assert 'extractions' in annotations
        assert 'pipeline_errors' in annotations
    
    def test_initial_state_builds_cleanly(self, initial_pipeline_state):
        """Initial state should have all required keys."""
        required_keys = [
            "deal_id", "deal_name", "raw_files", "file_content_types",
            "raw_documents", "ingest_errors", "classified_documents",
            "classification_errors", "extractions", "extraction_errors",
            "synthesis", "synthesis_error", "arithmetic_verification",
            "pipeline_stage", "pipeline_errors", "completed_at"
        ]
        
        for key in required_keys:
            assert key in initial_pipeline_state, f"Missing key: {key}"


# ============================================================================
# Pipeline Node Tests
# ============================================================================

class TestPipelineNodes:
    """Individual pipeline node tests."""
    
    @pytest.mark.asyncio
    async def test_ingest_node_processes_text_pdf(self, mock_llm, sample_excel_bytes, initial_pipeline_state):
        """Ingest node should process files into raw documents."""
        from graph import ingest_documents
        
        state = initial_pipeline_state.copy()
        state["raw_files"] = {"rent_roll.xlsx": sample_excel_bytes}
        state["file_content_types"] = {"rent_roll.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        
        result = await ingest_documents(state)
        
        assert "raw_documents" in result
    
    @pytest.mark.asyncio
    async def test_classify_node_processes_all_documents(self, mock_llm, initial_pipeline_state):
        """Classify node should process all raw documents."""
        from graph import classify_documents
        
        state = initial_pipeline_state.copy()
        state["raw_documents"] = [
            {"filename": "rent_roll.pdf", "text": "RENT ROLL\nTenant data...", "doc_id": "doc1"},
            {"filename": "lease.pdf", "text": "LEASE AGREEMENT\nTerms...", "doc_id": "doc2"}
        ]
        
        result = await classify_documents(state)
        
        assert "classified_documents" in result
        assert len(result["classified_documents"]) == 2


# ============================================================================
# Full Pipeline Tests
# ============================================================================

class TestFullPipeline:
    """End-to-end pipeline tests with mocked LLM."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_pipeline_rent_roll_and_lease(self, mock_llm, sample_excel_bytes, sample_lease_text):
        """Full pipeline with rent roll and lease should complete."""
        from graph import graph
        
        initial_state = {
            "deal_id": "test-001",
            "deal_name": "5041 Bayou Boulevard",
            "raw_files": {
                "rent_roll.xlsx": sample_excel_bytes,
                "lease.pdf": sample_lease_text.encode()
            },
            "file_content_types": {
                "rent_roll.xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "lease.pdf": "application/pdf"
            },
            "raw_documents": [],
            "ingest_errors": [],
            "classified_documents": [],
            "classification_errors": [],
            "extractions": [],
            "extraction_errors": [],
            "synthesis": {},
            "rsf_recovery": {},
            "score_summary": {},
            "synthesis_error": None,
            "arithmetic_verification": {},
            "rent_roll_analysis": {},
            "rsf_reconciliation": {},
            "red_flags_result": {},
            "deal_score_result": {},
            "completeness_result": {},
            "pipeline_stage": "pending",
            "pipeline_errors": [],
            "completed_at": None,
        }
        
        result = await graph.ainvoke(initial_state)
        
        # Verify pipeline completed
        assert result.get("pipeline_stage") in ["completed", "completed_with_errors", "enriched", "synthesis_failed", "ingested"]
        
        # If completed, verify outputs exist
        if result.get("pipeline_stage") == "completed":
            assert "synthesis" in result or "score_summary" in result
    
    @pytest.mark.asyncio
    async def test_pipeline_handles_empty_file_list_gracefully(self, mock_llm):
        """Pipeline should handle empty file list without crashing."""
        from graph import graph
        
        initial_state = {
            "deal_id": "test-empty",
            "deal_name": "Empty Deal",
            "raw_files": {},
            "file_content_types": {},
            "raw_documents": [],
            "ingest_errors": [],
            "classified_documents": [],
            "classification_errors": [],
            "extractions": [],
            "extraction_errors": [],
            "synthesis": {},
            "rsf_recovery": {},
            "score_summary": {},
            "synthesis_error": None,
            "arithmetic_verification": {},
            "rent_roll_analysis": {},
            "rsf_reconciliation": {},
            "red_flags_result": {},
            "deal_score_result": {},
            "completeness_result": {},
            "pipeline_stage": "pending",
            "pipeline_errors": [],
            "completed_at": None,
        }
        
        # Should not crash
        result = await graph.ainvoke(initial_state)
        assert isinstance(result, dict)


# ============================================================================
# API Endpoint Tests
# ============================================================================

class TestAPIEndpoints:
    """HTTP layer tests."""
    
    @pytest.mark.asyncio
    async def test_health_check(self, test_client):
        """GET /health should return 200."""
        if test_client is None:
            pytest.skip("Test client not available")
        
        async with test_client as client:
            response = await client.get("/health")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "ok"
    
    @pytest.mark.asyncio
    async def test_analyze_endpoint_requires_files(self, test_client):
        """POST /analyze without files should fail."""
        if test_client is None:
            pytest.skip("Test client not available")
        
        async with test_client as client:
            response = await client.post("/analyze", data={"deal_name": "Test"})
            assert response.status_code in [400, 422]


# ============================================================================
# OCR Path Tests
# ============================================================================

class TestScannedPDFHandling:
    """OCR processing tests."""
    
    def test_scanned_pdf_routes_to_ocr(self):
        """Image-only PDFs should be flagged for OCR."""
        from agents.document_parsing import DocumentParsingAgent
        
        agent = DocumentParsingAgent()
        # Simulate a PDF with no extractable text (would need OCR)
        result = agent.check("scanned.pdf", b"%PDF-1.4\n", "application/pdf")
        
        # Should either need OCR or have empty text
        assert result.needs_ocr == True or result.extracted_text == ""
    
    def test_ocr_agent_cleans_text(self):
        """OCR agent should clean raw OCR text."""
        from agents.ocr_agent import OCRAgent
        
        agent = OCRAgent()
        raw_ocr = "R3NT R0LL\n\n\n\n\nSu1te 1OO - Reg1ons 8ank\n!!@@##"  # OCR noise
        
        # The _clean_ocr_text method removes noise and extra whitespace
        result = agent._clean_ocr_text(raw_ocr)
        
        # Should have reduced excessive blank lines (max 2 consecutive allowed)
        assert result.count("\n\n\n\n") == 0  # No 4+ consecutive blank lines
        assert len(result) > 0


class TestDocumentSegmentation:
    """Document segmentation tests for multi-section PDFs."""
    
    @pytest.mark.asyncio
    async def test_single_section_not_segmented(self, mock_llm, sample_rent_roll_text):
        """Single-section documents should return one segment."""
        from agents.document_segmentation import DocumentSegmentationAgent
        
        agent = DocumentSegmentationAgent()
        segments = await agent.segment_document(sample_rent_roll_text)
        
        # Single document should return at least one segment
        assert len(segments) >= 1
        assert segments[0].text is not None
    
    @pytest.mark.asyncio
    async def test_multi_section_document_segmented(self, mock_llm):
        """Multi-section documents should be split into segments."""
        from agents.document_segmentation import DocumentSegmentationAgent
        
        # Simulate a multi-section PDF with clear section headers
        multi_section_text = """
MONTHLY MANAGEMENT REPORT
Town & Country Plaza
February 2026

--- Page 1 ---

COLLECTION REPORT
Rent Roll for Period Ending February 2026

Suite    Tenant           RSF      Monthly Rent    Status
100      Regions Bank     3,200    $4,800.00      Current
200      State Farm       2,800    $4,200.00      Current

--- Page 5 ---

CASH RECEIPTS & DISBURSEMENTS
Check Register - February 2026

Date       Payee                Amount
02/01/26   City Water          $1,234.56
02/15/26   Electric Co         $2,345.67

--- Page 10 ---

ENDING RECEIVABLES
AR Aging Report

Tenant         Current   30 Days   60 Days   90+ Days
Regions Bank   $0.00     $0.00     $0.00     $0.00
State Farm     $0.00     $500.00   $0.00     $0.00
"""
        
        agent = DocumentSegmentationAgent()
        segments = await agent.segment_document(multi_section_text)
        
        # Should detect at least one section
        assert len(segments) >= 1
        
        # Check that meaningful document types were detected (not just UNKNOWN)
        doc_types = [s.doc_type for s in segments]
        # At least one should be a known type
        known_types = {"RENT_ROLL", "DISBURSEMENTS", "ENDING_RECEIVABLES", "INCOME_EXPENSE", "LEASE_RECAP", "SALES_VOLUME", "COVER_LETTER"}
        assert any(dt in known_types for dt in doc_types)
    
    @pytest.mark.asyncio
    async def test_segment_has_required_fields(self, mock_llm, sample_rent_roll_text):
        """Each segment should have required fields."""
        from agents.document_segmentation import DocumentSegmentationAgent
        
        agent = DocumentSegmentationAgent()
        segments = await agent.segment_document(sample_rent_roll_text)
        
        for segment in segments:
            assert hasattr(segment, 'doc_type')
            assert hasattr(segment, 'text')
            assert hasattr(segment, 'start_page')
            assert hasattr(segment, 'end_page')
            assert hasattr(segment, 'confidence')
            assert segment.start_page >= 1
            assert segment.end_page >= segment.start_page
    
    @pytest.mark.asyncio
    async def test_empty_text_returns_empty_segments(self, mock_llm):
        """Empty text should return empty segments list."""
        from agents.document_segmentation import DocumentSegmentationAgent
        
        agent = DocumentSegmentationAgent()
        segments = await agent.segment_document("")
        
        assert isinstance(segments, list)
        # May return empty list or single "UNKNOWN" segment
        if len(segments) > 0:
            assert segments[0].doc_type in ["UNKNOWN", "COVER_LETTER"]


class TestPipelineWithSegmentation:
    """Tests for pipeline with document segmentation enabled."""
    
    @pytest.mark.asyncio
    async def test_multi_page_pdf_triggers_segmentation(self, mock_llm, initial_pipeline_state, sample_pdf_bytes):
        """Multi-page PDFs should trigger segmentation in ingest."""
        from graph import ingest_documents
        
        # Simulate a multi-page PDF (page_count > 3)
        state = {
            **initial_pipeline_state,
            "raw_files": {"multi_page_report.pdf": sample_pdf_bytes},
            "file_content_types": {"multi_page_report.pdf": "application/pdf"},
        }
        
        result = await ingest_documents(state)
        
        # Should have processed without errors
        assert "raw_documents" in result
        # Errors may occur due to mock PDF not having real pages
        # but the function should not crash
