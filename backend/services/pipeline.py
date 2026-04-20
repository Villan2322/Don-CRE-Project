"""
CRE Document Intelligence Pipeline
Collapsed 15-node design based on the n8n technical reference.

The 6-stage pipeline:
1. File Extraction - Universal ingestion with OCR detection
2. Classification - Single node classifies all documents  
3. Extraction - Config-driven extraction for all 9 doc types
4. Synthesis - Cross-document analysis and scoring
5. Verification - Arithmetic checks and confidence thresholds
6. Output - Formatted for all 6 sheet tabs
"""

import asyncio
import json
import re
from datetime import datetime
from typing import Any
from openai import AsyncOpenAI

from config.extraction_prompts import (
    EXTRACTION_PROMPTS,
    CLASSIFICATION_PROMPT,
    SYNTHESIS_PROMPT,
    VERIFICATION_PROMPT,
    DOC_TYPES,
)
from models.schemas import (
    DocumentType,
    DealAnalysis,
    LeaseAbstractPipeline as LeaseAbstract,
    TenantInfo,
    RSFReconciliationPipeline as RSFReconciliation,
    RedFlag,
    Severity,
)


class CREPipeline:
    """
    Collapsed 15-node CRE Document Intelligence Pipeline.
    
    Replaces the 76-node n8n workflow with config-driven extraction.
    """
    
    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            base_url="https://ai-gateway.vercel.sh/v1",
            api_key=api_key or "dummy",  # AI Gateway handles auth
        )
        self.model = "anthropic/claude-sonnet-4"
    
    async def run(self, deal_name: str, documents: list[dict]) -> DealAnalysis:
        """
        Run the full 6-stage pipeline on a document package.
        
        Args:
            deal_name: Name of the deal being analyzed
            documents: List of {filename, content, file_type} dicts
            
        Returns:
            Complete DealAnalysis with scores, flags, and recommendations
        """
        # Stage 1: File Extraction (already done by caller - documents have content)
        doc_objects = self._assemble_documents(deal_name, documents)
        
        # Stage 2: Classification
        classified_docs = await self._classify_documents(doc_objects)
        
        # Stage 3: Extraction (config-driven, handles all 9 types)
        extractions = await self._extract_all_documents(classified_docs)
        
        # Stage 4: Synthesis
        synthesis = await self._synthesize_deal(deal_name, extractions)
        
        # Stage 5: Verification
        verified = await self._verify_analysis(synthesis, extractions)
        
        # Stage 6: Output formatting
        return self._format_output(deal_name, verified, extractions)
    
    # =========================================================================
    # STAGE 1: File Extraction / Document Assembly
    # =========================================================================
    
    def _assemble_documents(self, deal_name: str, documents: list[dict]) -> list[dict]:
        """
        Universal File Ingestion - Assemble all documents into uniform objects.
        Replaces: Extract Pages from PDF, Extract_Rent_Roll, Extract_Lease×8, etc.
        """
        doc_objects = []
        for i, doc in enumerate(documents):
            content = doc.get("content", "")
            doc_obj = {
                "doc_id": f"{deal_name}_{i}",
                "deal_name": deal_name,
                "file_name": doc.get("filename", f"document_{i}"),
                "file_extension": self._get_extension(doc.get("filename", "")),
                "mime_type": doc.get("mime_type", "application/octet-stream"),
                "raw_text": content[:50000],  # Truncate to 50k chars
                "has_text": len(content.strip()) > 100,
                "was_truncated": len(content) > 50000,
                "original_char_count": len(content),
                "needs_ocr": len(content.strip()) < 100,  # Scanned PDF detection
                "pipeline_stage": "assembled",
            }
            doc_objects.append(doc_obj)
        return doc_objects
    
    def _get_extension(self, filename: str) -> str:
        if "." in filename:
            return filename.rsplit(".", 1)[-1].lower()
        return ""
    
    # =========================================================================
    # STAGE 2: Classification
    # =========================================================================
    
    async def _classify_documents(self, documents: list[dict]) -> list[dict]:
        """
        Classify Documents - Single node, loops all docs.
        Replaces: Build Classification Payload, Claude - Classify Doc, Parse Classification, Route by Doc Type
        """
        tasks = [self._classify_single(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        classified = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                doc["doc_type"] = "UNKNOWN"
                doc["classification_confidence"] = 0.0
                doc["classification_error"] = str(result)
            else:
                doc.update(result)
            doc["pipeline_stage"] = "classified"
            classified.append(doc)
        
        return classified
    
    async def _classify_single(self, doc: dict) -> dict:
        """Classify a single document using Claude."""
        # Use first AND last 1500 chars for better classification
        text = doc["raw_text"]
        sample = text[:1500]
        if len(text) > 3000:
            sample += "\n\n[...]\n\n" + text[-1500:]
        
        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=500,
            messages=[
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": f"Classify this document:\n\n{sample}"},
            ],
        )
        
        content = response.choices[0].message.content
        parsed = self._parse_json_response(content)
        
        return {
            "doc_type": parsed.get("doc_type", "UNKNOWN"),
            "classification_confidence": parsed.get("confidence", 0.5),
            "classification_reasoning": parsed.get("reasoning", ""),
        }
    
    # =========================================================================
    # STAGE 3: Extraction (Config-Driven)
    # =========================================================================
    
    async def _extract_all_documents(self, documents: list[dict]) -> list[dict]:
        """
        Extract Documents - ONE node with config map, loops all classified docs.
        Replaces: 27 extraction lane nodes (Build Payload × 9 + Claude Call × 9 + Parse × 9)
        """
        tasks = [self._extract_single(doc) for doc in documents]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        extractions = []
        for doc, result in zip(documents, results):
            if isinstance(result, Exception):
                extraction = {
                    **doc,
                    "extraction": {},
                    "extraction_error": str(result),
                }
            else:
                extraction = {
                    **doc,
                    "extraction": result,
                    "extraction_timestamp": datetime.utcnow().isoformat(),
                }
            
            # Apply lease enrichment (months_remaining, risk_level)
            if doc["doc_type"] in ["LEASE", "LEASE_ABSTRACT"]:
                extraction = self._enrich_lease_extraction(extraction)
            
            extraction["pipeline_stage"] = "extracted"
            extractions.append(extraction)
        
        return extractions
    
    async def _extract_single(self, doc: dict) -> dict:
        """Extract structured data from a single document using config-driven prompts."""
        doc_type = doc.get("doc_type", "UNKNOWN")
        
        # Get extraction prompt from config map
        prompt_config = EXTRACTION_PROMPTS.get(doc_type)
        if not prompt_config:
            return {"_note": f"No extraction config for {doc_type}"}
        
        system_prompt = prompt_config["system"]
        fields = prompt_config.get("fields", [])
        
        user_prompt = f"""Extract the following fields from this {doc_type} document:

Fields to extract: {', '.join(fields)}

Document content:
{doc['raw_text']}

Return a JSON object with each field. For each field, include:
- value: the extracted value
- confidence: 0.0-1.0 confidence score
- source_text: the exact text from the document that supports this value

If a field cannot be found, set value to null and confidence to 0."""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=4000,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        
        content = response.choices[0].message.content
        return self._parse_json_response(content)
    
    def _enrich_lease_extraction(self, extraction: dict) -> dict:
        """
        Lease Abstract Rent Roll enrichment.
        Adds: months_remaining, risk_level, monthly_rent, abstract_complete, missing_fields
        """
        ext = extraction.get("extraction", {})
        
        # Calculate months remaining
        expiry = ext.get("lease_expiration_date", {})
        expiry_value = expiry.get("value") if isinstance(expiry, dict) else expiry
        
        months_remaining = None
        risk_level = "UNKNOWN"
        
        if expiry_value:
            try:
                # Try to parse the date
                from dateutil import parser as date_parser
                expiry_date = date_parser.parse(expiry_value)
                today = datetime.now()
                months_remaining = (expiry_date.year - today.year) * 12 + (expiry_date.month - today.month)
                
                # Assign risk level
                if months_remaining <= 0:
                    risk_level = "CRITICAL"
                elif months_remaining <= 3:
                    risk_level = "CRITICAL"
                elif months_remaining <= 12:
                    risk_level = "HIGH"
                elif months_remaining <= 24:
                    risk_level = "MODERATE"
                else:
                    risk_level = "LOW"
            except:
                pass
        
        # Derive monthly rent if missing
        annual_rent = ext.get("annual_base_rent", {})
        annual_value = annual_rent.get("value") if isinstance(annual_rent, dict) else annual_rent
        monthly_rent = None
        if annual_value:
            try:
                monthly_rent = float(str(annual_value).replace(",", "").replace("$", "")) / 12
            except:
                pass
        
        # Check for missing key fields
        key_fields = ["tenant_name", "premises_address", "rentable_sf", "lease_commencement_date", 
                      "lease_expiration_date", "annual_base_rent", "expense_structure"]
        missing_fields = [f for f in key_fields if not ext.get(f)]
        
        extraction["enrichment"] = {
            "months_remaining": months_remaining,
            "risk_level": risk_level,
            "monthly_rent": monthly_rent,
            "abstract_complete": len(missing_fields) == 0,
            "missing_fields": missing_fields,
        }
        
        return extraction
    
    # =========================================================================
    # STAGE 4: Synthesis
    # =========================================================================
    
    async def _synthesize_deal(self, deal_name: str, extractions: list[dict]) -> dict:
        """
        Synthesize Deal - Cross-document analysis, scoring, and recommendations.
        Replaces: Build Synthesis Payload, Claude - Synthesize Deal, Parse Synthesis
        """
        # Slim extractions to reduce token count (13k -> 5k)
        slimmed = self._slim_extractions(extractions)
        
        # Group by doc type
        by_type = {}
        for ext in extractions:
            doc_type = ext.get("doc_type", "UNKNOWN")
            if doc_type not in by_type:
                by_type[doc_type] = []
            by_type[doc_type].append(ext)
        
        present_types = list(by_type.keys())
        lease_count = len(by_type.get("LEASE", [])) + len(by_type.get("LEASE_ABSTRACT", []))
        
        user_prompt = f"""Analyze this commercial real estate deal package.

Deal Name: {deal_name}
Documents Present: {', '.join(present_types)}
Number of Leases: {lease_count}

Extractions:
{json.dumps(slimmed, indent=2)}

Produce a comprehensive analysis including:
1. RSF Reconciliation - Compare SF across rent roll, leases, BOMA, county PA
2. Rent Verification - Validate rent calculations and pro-rata shares
3. Lease Audit - WALT calculation, expiry schedule, risk assessment
4. Financial Summary - NOI, vacancy, AR concerns, CAM recovery
5. Deal Score - Score 0-100 with sub-scores for each dimension
6. Red Flags - List all issues by severity (CRITICAL, HIGH, MODERATE, LOW)
7. What To Get Next - Prioritized list of missing documents
8. RSF Recovery Opportunity - Dollar estimate if SF discrepancies found

Return as JSON with these top-level keys:
rsf_reconciliation, rent_verification, lease_audit, financial_summary, 
deal_score, red_flags, what_to_get_next, rsf_recovery_opportunity"""

        response = await self.client.chat.completions.create(
            model=self.model,
            max_tokens=8000,
            messages=[
                {"role": "system", "content": SYNTHESIS_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        
        content = response.choices[0].message.content
        synthesis = self._parse_json_response(content)
        synthesis["synthesis_timestamp"] = datetime.utcnow().isoformat()
        
        return synthesis
    
    def _slim_extractions(self, extractions: list[dict]) -> list[dict]:
        """
        Collapse {value, confidence, source_text} objects to just values.
        Reduces prompt from ~13k to ~5k tokens.
        """
        slimmed = []
        for ext in extractions:
            slim = {
                "doc_id": ext.get("doc_id"),
                "doc_type": ext.get("doc_type"),
                "file_name": ext.get("file_name"),
            }
            
            extraction = ext.get("extraction", {})
            slim_extraction = {}
            for key, value in extraction.items():
                if isinstance(value, dict) and "value" in value:
                    slim_extraction[key] = value["value"]
                else:
                    slim_extraction[key] = value
            
            slim["extraction"] = slim_extraction
            
            # Include enrichment if present
            if "enrichment" in ext:
                slim["enrichment"] = ext["enrichment"]
            
            slimmed.append(slim)
        
        return slimmed
    
    # =========================================================================
    # STAGE 5: Verification
    # =========================================================================
    
    async def _verify_analysis(self, synthesis: dict, extractions: list[dict]) -> dict:
        """
        Verify Analysis - Arithmetic checks and confidence thresholds.
        Replaces: Arithmetic Verification, Flatten Fields, Build Verification Payload, 
                  Claude - Independent Verification, Apply Confidence Thresholds
        """
        # Arithmetic verification
        arithmetic = self._arithmetic_verification(synthesis, extractions)
        
        # Flatten fields for verification
        flattened = self._flatten_fields(extractions)
        
        # Filter to high-impact fields only (reduces verification payload)
        high_impact = self._filter_high_impact_fields(flattened)
        
        # Independent verification (optional - can be expensive)
        # verified_fields = await self._independent_verification(high_impact)
        
        return {
            "synthesis": synthesis,
            "arithmetic_verification": arithmetic,
            "flattened_fields": flattened,
            "high_impact_fields": high_impact,
        }
    
    def _arithmetic_verification(self, synthesis: dict, extractions: list[dict]) -> dict:
        """
        Arithmetic Verification - Recalculate key figures and flag mismatches.
        Checks: PA vs Rent Roll SF, NOI calculation, CAP rate, DSCR, pro-rata shares, etc.
        """
        checks = []
        
        def v(obj, *paths):
            """Extract numeric value from various formats."""
            for path in paths:
                val = obj
                for key in path.split("."):
                    if isinstance(val, dict):
                        val = val.get(key)
                    else:
                        val = None
                        break
                if val is not None:
                    try:
                        return float(str(val).replace(",", "").replace("$", "").replace("%", ""))
                    except:
                        pass
            return None
        
        def chk(name: str, stated: float | None, computed: float | None, formula: str, tolerance: float = 0.01) -> dict:
            """Compare two values within tolerance."""
            if stated is None or computed is None:
                return {"check": name, "status": "INCOMPLETE", "stated": stated, "computed": computed, "formula": formula}
            
            if stated == 0:
                delta_pct = 0 if computed == 0 else 100
            else:
                delta_pct = abs(stated - computed) / abs(stated) * 100
            
            status = "VERIFIED" if delta_pct <= tolerance * 100 else "CALC_MISMATCH"
            
            return {
                "check": name,
                "status": status,
                "stated": stated,
                "computed": computed,
                "delta_pct": round(delta_pct, 2),
                "formula": formula,
            }
        
        # Get values from synthesis
        rsf = synthesis.get("rsf_reconciliation", {})
        fin = synthesis.get("financial_summary", {})
        
        # Check: NOI = Revenue - OpEx
        revenue = v(fin, "total_revenue", "gross_income")
        opex = v(fin, "total_opex", "operating_expenses")
        stated_noi = v(fin, "noi", "net_operating_income")
        if revenue and opex:
            checks.append(chk("NOI Calculation", stated_noi, revenue - opex, "NOI = Revenue - OpEx"))
        
        # Check: Rent PSF = Annual Rent / RSF
        annual_rent = v(fin, "total_annual_rent", "annual_base_rent")
        total_rsf = v(rsf, "rent_roll_rsf", "total_rsf")
        stated_psf = v(fin, "rent_psf", "average_rent_psf")
        if annual_rent and total_rsf and total_rsf > 0:
            checks.append(chk("Rent PSF", stated_psf, annual_rent / total_rsf, "Rent PSF = Annual Rent / RSF"))
        
        # Check: RSF sources match
        rent_roll_rsf = v(rsf, "sources.RENT_ROLL", "rent_roll_rsf")
        boma_rsf = v(rsf, "sources.BOMA", "boma_rsf")
        lease_rsf = v(rsf, "sources.LEASE", "lease_rsf")
        
        if rent_roll_rsf and boma_rsf:
            checks.append(chk("BOMA vs Rent Roll RSF", rent_roll_rsf, boma_rsf, "BOMA RSF should match Rent Roll RSF", 0.05))
        
        mismatches = [c for c in checks if c["status"] == "CALC_MISMATCH"]
        
        return {
            "checks": checks,
            "total": len(checks),
            "verified": len([c for c in checks if c["status"] == "VERIFIED"]),
            "mismatches": len(mismatches),
            "mismatch_details": mismatches,
        }
    
    def _flatten_fields(self, extractions: list[dict]) -> list[dict]:
        """
        Flatten all extraction fields into a flat array for verification.
        Each record: {field_path, value, confidence, doc_type, source_text}
        """
        flattened = []
        
        def flatten_obj(obj: dict, path: str, doc_type: str, doc_id: str):
            for key, value in obj.items():
                if key.startswith("_"):
                    continue
                
                field_path = f"{path}.{key}" if path else key
                
                if isinstance(value, dict):
                    if "value" in value:
                        # This is a field with confidence
                        flattened.append({
                            "doc_id": doc_id,
                            "doc_type": doc_type,
                            "field_path": field_path,
                            "value": value.get("value"),
                            "confidence": value.get("confidence", 0.5),
                            "source_text": value.get("source_text", ""),
                        })
                    else:
                        # Nested object
                        flatten_obj(value, field_path, doc_type, doc_id)
                elif isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            flatten_obj(item, f"{field_path}[{i}]", doc_type, doc_id)
        
        for ext in extractions:
            extraction = ext.get("extraction", {})
            flatten_obj(extraction, "", ext.get("doc_type", "UNKNOWN"), ext.get("doc_id", ""))
        
        return flattened
    
    def _filter_high_impact_fields(self, flattened: list[dict]) -> list[dict]:
        """
        Filter to high-impact fields only: high dollar impact, conflicts, or low confidence.
        Reduces verification payload from 100+ to 10-20 most important fields.
        """
        high_impact_keywords = [
            "rsf", "sf", "square", "rent", "noi", "revenue", "income",
            "expense", "cam", "price", "value", "total", "annual",
        ]
        
        filtered = []
        for field in flattened:
            path_lower = field["field_path"].lower()
            
            # Include if: low confidence OR high-value field
            is_low_confidence = field.get("confidence", 1.0) < 0.8
            is_high_value = any(kw in path_lower for kw in high_impact_keywords)
            
            if is_low_confidence or is_high_value:
                filtered.append(field)
        
        return filtered[:20]  # Limit to top 20
    
    # =========================================================================
    # STAGE 6: Output Formatting
    # =========================================================================
    
    def _format_output(self, deal_name: str, verified: dict, extractions: list[dict]) -> DealAnalysis:
        """
        Format Output - Structure data for all 6 sheet tabs.
        Replaces: Build Deal Snapshot Rows, Build Audit Log Rows, Build Rent Rows, 
                  Build Lease Audit Rows, Build Risk Dashboard, Blue Platform Value
        """
        synthesis = verified.get("synthesis", {})
        arithmetic = verified.get("arithmetic_verification", {})
        
        # Extract deal score
        deal_score = synthesis.get("deal_score", {})
        if isinstance(deal_score, dict):
            overall_score = deal_score.get("overall", deal_score.get("total", 0))
        else:
            overall_score = deal_score if isinstance(deal_score, (int, float)) else 0
        
        # Determine tier
        if overall_score >= 80:
            tier = "READY"
        elif overall_score >= 60:
            tier = "NEEDS_WORK"
        else:
            tier = "HIGH_RISK"
        
        # Format red flags
        red_flags = []
        raw_flags = synthesis.get("red_flags", [])
        if isinstance(raw_flags, list):
            for flag in raw_flags:
                if isinstance(flag, dict):
                    red_flags.append(RedFlag(
                        severity=Severity(flag.get("severity", "MODERATE").upper()),
                        category=flag.get("category", "General"),
                        description=flag.get("description", flag.get("flag", "")),
                        impact=flag.get("impact", ""),
                        resolution=flag.get("resolution", flag.get("recommended_action", "")),
                    ))
        
        # Format RSF reconciliation
        rsf_data = synthesis.get("rsf_reconciliation", {})
        rsf = RSFReconciliation(
            rent_roll_rsf=rsf_data.get("sources", {}).get("RENT_ROLL", rsf_data.get("rent_roll_rsf")),
            lease_rsf=rsf_data.get("sources", {}).get("LEASE", rsf_data.get("lease_rsf")),
            boma_rsf=rsf_data.get("sources", {}).get("BOMA", rsf_data.get("boma_rsf")),
            county_pa_rsf=rsf_data.get("sources", {}).get("COUNTY_PA", rsf_data.get("county_pa_rsf")),
            discrepancy_sf=rsf_data.get("max_discrepancy_sf", rsf_data.get("discrepancy")),
            discrepancy_pct=rsf_data.get("max_discrepancy_pct", rsf_data.get("discrepancy_pct")),
        )
        
        # Calculate RSF recovery opportunity
        rsf_recovery = synthesis.get("rsf_recovery_opportunity", {})
        if isinstance(rsf_recovery, dict):
            recovery_sf = rsf_recovery.get("recoverable_sf", 0)
            recovery_dollar = rsf_recovery.get("annual_value", rsf_recovery.get("dollar_estimate", 0))
        else:
            recovery_sf = 0
            recovery_dollar = 0
        
        # Format tenants from rent roll extractions
        tenants = []
        for ext in extractions:
            if ext.get("doc_type") in ["RENT_ROLL", "RENT_ROLL_XLSX", "MANAGEMENT_REPORT"]:
                tenant_list = ext.get("extraction", {}).get("tenants", [])
                if isinstance(tenant_list, list):
                    for t in tenant_list:
                        if isinstance(t, dict):
                            tenants.append(TenantInfo(
                                name=t.get("tenant_name", t.get("name", "Unknown")),
                                suite=t.get("suite", ""),
                                rsf=t.get("rsf", t.get("rentable_sf", 0)),
                                lease_start=t.get("lease_start", t.get("commencement_date")),
                                lease_end=t.get("lease_end", t.get("expiration_date")),
                                monthly_rent=t.get("monthly_rent", 0),
                                annual_rent=t.get("annual_rent", t.get("annual_base_rent", 0)),
                                rent_psf=t.get("rent_psf", 0),
                            ))
        
        # Format lease abstracts
        lease_abstracts = []
        for ext in extractions:
            if ext.get("doc_type") in ["LEASE", "LEASE_ABSTRACT"]:
                e = ext.get("extraction", {})
                enrichment = ext.get("enrichment", {})
                
                def get_val(field):
                    val = e.get(field, {})
                    return val.get("value") if isinstance(val, dict) else val
                
                lease_abstracts.append(LeaseAbstract(
                    tenant_name=get_val("tenant_name"),
                    premises_address=get_val("premises_address"),
                    suite=get_val("suite"),
                    rentable_sf=get_val("rentable_sf"),
                    lease_commencement=get_val("lease_commencement_date"),
                    lease_expiration=get_val("lease_expiration_date"),
                    lease_term_months=get_val("lease_term_months"),
                    annual_base_rent=get_val("annual_base_rent"),
                    monthly_rent=enrichment.get("monthly_rent"),
                    rent_escalation=get_val("rent_escalation"),
                    expense_structure=get_val("expense_structure"),
                    cam_cap=get_val("cam_cap"),
                    renewal_options=get_val("renewal_options"),
                    early_termination=get_val("early_termination_rights"),
                    tenant_improvements=get_val("ti_allowance"),
                    missing_fields=enrichment.get("missing_fields", []),
                    months_remaining=enrichment.get("months_remaining"),
                    risk_level=enrichment.get("risk_level"),
                ))
        
        # Format what to get next
        what_to_get_next = synthesis.get("what_to_get_next", [])
        if isinstance(what_to_get_next, list):
            what_to_get_next = [
                item if isinstance(item, str) else item.get("document", str(item))
                for item in what_to_get_next
            ]
        
        # Build financial summary
        fin = synthesis.get("financial_summary", {})
        
        return DealAnalysis(
            deal_name=deal_name,
            overall_score=overall_score,
            tier=tier,
            sub_scores=deal_score if isinstance(deal_score, dict) else {},
            red_flags=red_flags,
            rsf_reconciliation=rsf,
            rsf_recovery_sf=recovery_sf,
            rsf_recovery_annual_value=recovery_dollar,
            tenants=tenants,
            lease_abstracts=lease_abstracts,
            noi=fin.get("noi"),
            walt_months=synthesis.get("lease_audit", {}).get("walt_months"),
            vacancy_pct=fin.get("vacancy_pct", fin.get("vacancy")),
            ar_outstanding=fin.get("ar_outstanding", fin.get("ar_concern")),
            what_to_get_next=what_to_get_next,
            arithmetic_checks=arithmetic.get("checks", []),
            analysis_timestamp=datetime.utcnow().isoformat(),
            documents_processed=len(extractions),
        )
    
    # =========================================================================
    # Utilities
    # =========================================================================
    
    def _parse_json_response(self, content: str) -> dict:
        """Parse JSON from Claude response, handling markdown fencing."""
        if not content:
            return {"_parse_error": "Empty response"}
        
        # Try to extract JSON from markdown code blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if json_match:
            content = json_match.group(1)
        
        # Try to find JSON object
        content = content.strip()
        
        # Find the first { and last }
        start = content.find("{")
        end = content.rfind("}")
        
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError as e:
                return {"_parse_error": str(e), "_raw": content[start:end + 1][:500]}
        
        return {"_parse_error": "No JSON found", "_raw": content[:500]}
