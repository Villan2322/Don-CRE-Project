"""
Synthesis Agent
The main intelligence layer - combines all extractions into deal analysis.
Replaces Build Synthesis Payload + Claude - Synthesize Deal + Parse Synthesis from n8n.
"""

import json
import re
from datetime import datetime
from typing import Any

from .base import BaseAgent
from ..config.extraction_prompts import SYNTHESIS_PROMPT


class SynthesisAgent(BaseAgent):
    """
    Synthesizes all document extractions into a unified deal analysis.
    This is the most expensive and important call in the pipeline.
    """
    
    def __init__(self):
        super().__init__()
    
    async def synthesize_deal(
        self,
        extractions: list[dict],
        deal_name: str
    ) -> dict[str, Any]:
        """
        Run the main synthesis call that produces cross-document analysis.
        """
        # Group extractions by doc_type
        grouped = self._group_extractions(extractions)
        
        # Slim the extractions to reduce token count (per tech ref)
        slimmed = self._slim_extractions(grouped)
        
        # Build the prompt with present doc types
        doc_types_present = list(grouped.keys())
        lease_count = len(grouped.get("LEASE", []))
        
        prompt = SYNTHESIS_PROMPT.format(
            doc_types_present=", ".join(doc_types_present)
        )
        
        user_message = f"""Deal Name: {deal_name}
Document Types Present: {", ".join(doc_types_present)}
Number of Leases: {lease_count}

Extractions:
{json.dumps(slimmed, indent=2, default=str)}

Analyze this deal and return the synthesis JSON."""

        response = await self.call_llm(
            system_prompt=prompt,
            user_message=user_message,
            max_tokens=8000  # Large output for synthesis
        )
        
        try:
            synthesis = json.loads(self._extract_json(response))
            
            return {
                "deal_name": deal_name,
                "synthesis": synthesis,
                "raw_extractions": grouped,
                "doc_types_present": doc_types_present,
                "lease_count": lease_count,
                "score_summary": synthesis.get("deal_score", {}),
                "rsf_recovery": synthesis.get("rsf_recovery_opportunity", {}),
                "pipeline_stage": "synthesized",
                "synthesis_timestamp": datetime.utcnow().isoformat(),
                "_parse_error": None
            }
        except json.JSONDecodeError as e:
            # Critical: Don't silently fail - return error info (dynamic fix)
            return {
                "deal_name": deal_name,
                "synthesis": {},
                "raw_extractions": grouped,
                "doc_types_present": doc_types_present,
                "lease_count": lease_count,
                "score_summary": {},
                "rsf_recovery": {},
                "pipeline_stage": "synthesis_failed",
                "synthesis_timestamp": datetime.utcnow().isoformat(),
                "_parse_error": f"Synthesis JSON truncated or malformed: {str(e)}. Response end: {response[-500:]}"
            }
    
    def _group_extractions(self, extractions: list[dict]) -> dict[str, list]:
        """Group extractions by document type."""
        grouped: dict[str, list] = {}
        
        for ext in extractions:
            doc_type = ext.get("doc_type", "UNKNOWN")
            if doc_type not in grouped:
                grouped[doc_type] = []
            grouped[doc_type].append(ext)
        
        return grouped
    
    def _slim_extractions(self, grouped: dict[str, list]) -> dict:
        """
        Reduce extraction size by collapsing {value, confidence, source_text} to just value.
        Per tech ref: reduces prompt from ~13,000 tokens to ~5,000.
        """
        slimmed = {}
        
        for doc_type, extractions in grouped.items():
            slimmed[doc_type] = []
            
            for ext in extractions:
                slim_ext = {
                    "doc_id": ext.get("doc_id"),
                    "filename": ext.get("filename"),
                    "extraction": self._slim_object(ext.get("extraction", {}))
                }
                
                # Keep enriched data
                if "_enriched" in ext.get("extraction", {}):
                    slim_ext["_enriched"] = ext["extraction"]["_enriched"]
                
                slimmed[doc_type].append(slim_ext)
        
        return slimmed
    
    def _slim_object(self, obj: Any) -> Any:
        """Recursively slim an object by extracting just values."""
        if isinstance(obj, dict):
            # If it's a value/confidence/source_text object, extract just the value
            if "value" in obj and "confidence" in obj:
                return obj["value"]
            
            # Otherwise recurse
            return {k: self._slim_object(v) for k, v in obj.items() if not k.startswith("_")}
        
        elif isinstance(obj, list):
            return [self._slim_object(item) for item in obj]
        
        return obj
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from response, handling markdown fencing."""
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()
        
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json_match.group(0)
        
        return text


class ArithmeticVerificationAgent(BaseAgent):
    """
    Independent arithmetic verification.
    Recalculates key figures and flags mismatches.
    """
    
    TOLERANCE = 0.01  # 1% tolerance for floating point comparisons
    
    def verify_arithmetic(self, synthesis: dict, extractions: dict) -> dict:
        """
        Run arithmetic checks on the synthesis results.
        Returns verification results with VERIFIED, CALC_MISMATCH, or INCOMPLETE status.
        """
        checks = []
        
        # Get values from synthesis
        rsf = synthesis.get("rsf_reconciliation", {})
        financial = synthesis.get("financial_summary", {})
        
        # Check 1: Sum of tenant RSF vs total RSF
        if "RENT_ROLL" in extractions:
            rent_roll = extractions["RENT_ROLL"][0].get("extraction", {}) if extractions["RENT_ROLL"] else {}
            tenants = rent_roll.get("tenants", [])
            summary = rent_roll.get("summary", {})
            
            if tenants and summary:
                calculated_total = sum(t.get("rsf", 0) or 0 for t in tenants)
                stated_total = summary.get("total_rsf", 0)
                
                checks.append(self._check(
                    "Tenant RSF Sum",
                    calculated_total,
                    stated_total,
                    "sum(tenant.rsf)"
                ))
        
        # Check 2: NOI = Revenue - OpEx
        if financial:
            revenue = financial.get("effective_gross_income") or financial.get("total_annual_rent")
            opex = financial.get("operating_expenses")
            stated_noi = financial.get("noi")
            
            if revenue and opex and stated_noi:
                calculated_noi = revenue - opex
                checks.append(self._check(
                    "NOI Calculation",
                    calculated_noi,
                    stated_noi,
                    "Revenue - OpEx"
                ))
        
        # Check 3: Occupancy rate
        if "RENT_ROLL" in extractions:
            rent_roll = extractions["RENT_ROLL"][0].get("extraction", {}) if extractions["RENT_ROLL"] else {}
            summary = rent_roll.get("summary", {})
            
            if summary:
                occupied = summary.get("occupied_rsf", 0)
                total = summary.get("total_rsf", 0)
                stated_occ = summary.get("occupancy_rate", 0)
                
                if total > 0:
                    calculated_occ = (occupied / total) * 100
                    checks.append(self._check(
                        "Occupancy Rate",
                        calculated_occ,
                        stated_occ,
                        "(occupied_rsf / total_rsf) * 100"
                    ))
        
        # Check 4: RSF variance between sources
        if rsf:
            rr_rsf = rsf.get("sources", {}).get("RENT_ROLL", 0)
            boma_rsf = rsf.get("sources", {}).get("BOMA", 0)
            stated_variance = rsf.get("variance_rent_roll_vs_boma", 0)
            
            if rr_rsf and boma_rsf:
                calculated_variance = boma_rsf - rr_rsf
                
                # Mark as METHODOLOGY_DIFFERENCE if it matches canopy/porch from County PA
                status = self._check(
                    "RSF Variance (RR vs BOMA)",
                    calculated_variance,
                    stated_variance,
                    "BOMA_RSF - RENT_ROLL_RSF"
                )
                
                # Check if variance is explained by canopy/porch (dynamic fix)
                if "COUNTY_PA" in extractions:
                    county = extractions["COUNTY_PA"][0].get("extraction", {}) if extractions["COUNTY_PA"] else {}
                    canopy = county.get("canopy_sf", 0) or 0
                    porch = county.get("porch_sf", 0) or 0
                    
                    if abs(abs(calculated_variance) - (canopy + porch)) < 100:
                        status["note"] = "Variance explained by canopy/porch SF from County PA"
                        status["status"] = "METHODOLOGY_DIFFERENCE"
                
                checks.append(status)
        
        # Check 5: Rent PSF calculations
        if "LEASE" in extractions:
            for lease in extractions["LEASE"]:
                ext = lease.get("extraction", {})
                rsf_val = self._get_value(ext.get("rentable_sf"))
                annual_rent = self._get_value(ext.get("base_rent_annual"))
                stated_psf = self._get_value(ext.get("rent_per_sf"))
                
                if rsf_val and annual_rent and stated_psf:
                    calculated_psf = annual_rent / rsf_val
                    tenant = self._get_value(ext.get("tenant_name")) or "Unknown Tenant"
                    
                    checks.append(self._check(
                        f"Rent PSF - {tenant}",
                        calculated_psf,
                        stated_psf,
                        "annual_rent / rsf"
                    ))
        
        # Summary
        total = len(checks)
        mismatches = sum(1 for c in checks if c["status"] == "CALC_MISMATCH")
        incomplete = sum(1 for c in checks if c["status"] == "INCOMPLETE")
        
        return {
            "checks": checks,
            "total": total,
            "mismatches": mismatches,
            "incomplete": incomplete,
            "verified": total - mismatches - incomplete
        }
    
    def _check(self, name: str, calculated: float, stated: float, formula: str) -> dict:
        """Compare calculated vs stated value within tolerance."""
        if calculated is None or stated is None:
            return {
                "field": name,
                "llm_value": stated,
                "computed_value": None,
                "formula": formula,
                "status": "INCOMPLETE",
                "delta_pct": None
            }
        
        if stated == 0:
            delta_pct = 0 if calculated == 0 else float('inf')
        else:
            delta_pct = abs((calculated - stated) / stated)
        
        status = "VERIFIED" if delta_pct <= self.TOLERANCE else "CALC_MISMATCH"
        
        return {
            "field": name,
            "llm_value": stated,
            "computed_value": round(calculated, 2),
            "formula": formula,
            "status": status,
            "delta_pct": round(delta_pct * 100, 2)
        }
    
    def _get_value(self, field: Any) -> Any:
        """Extract value from field, handling {value, confidence} objects."""
        if isinstance(field, dict):
            return field.get("value")
        return field
