"""
Universal Extraction Agent
Replaces 9 separate extraction agents with a single config-driven extractor.
This is the "dynamic fix" described in the technical reference.
"""

import json
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Any, Optional

from agents.base import BaseAgent
from config.extraction_prompts import EXTRACTION_CONFIGS, CLASSIFICATION_PROMPT


class UniversalExtractor(BaseAgent):
    """
    A single extraction agent that handles all 9 document types.
    Reads extraction prompts from the config map instead of hardcoding.
    """
    
    def __init__(self):
        super().__init__()
        self.configs = EXTRACTION_CONFIGS
    
    async def classify_document(
        self, 
        text: str, 
        filename: str,
        mime_type: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Classify a document into one of 9 types.
        Uses first AND last 1500 chars for better classification (dynamic fix from tech ref).
        """
        # Use first and last portions for better classification
        text_sample = self._get_classification_sample(text)
        
        # Add filename hints to classification
        filename_hint = self._get_filename_hint(filename, mime_type)
        
        user_message = f"""Filename: {filename}
{filename_hint}

Document content (first and last portions):
{text_sample}

Classify this document."""

        response = await self.call_llm(
            system_prompt=CLASSIFICATION_PROMPT,
            user_message=user_message,
            max_tokens=500
        )
        
        try:
            classification = json.loads(self._extract_json(response))
            return {
                "doc_type": classification.get("document_type", "UNKNOWN"),
                "confidence": classification.get("confidence", 0.5),
                "reasoning": classification.get("reasoning", ""),
                "filename": filename
            }
        except json.JSONDecodeError:
            return {
                "doc_type": "UNKNOWN",
                "confidence": 0.0,
                "reasoning": f"Failed to parse classification response: {response[:200]}",
                "filename": filename
            }
    
    def _get_classification_sample(self, text: str, sample_size: int = 1500) -> str:
        """Get first AND last portions of text for better classification."""
        text = text.strip()
        if len(text) <= sample_size * 2:
            return text
        
        first_part = text[:sample_size]
        last_part = text[-sample_size:]
        return f"{first_part}\n\n[... middle content omitted ...]\n\n{last_part}"
    
    def _get_filename_hint(self, filename: str, mime_type: Optional[str]) -> str:
        """Generate hints based on filename and MIME type."""
        hints = []
        filename_lower = filename.lower()
        
        if "lease" in filename_lower:
            hints.append("Filename suggests this may be a lease document.")
        if "rent" in filename_lower and "roll" in filename_lower:
            hints.append("Filename suggests this may be a rent roll.")
        if "boma" in filename_lower:
            hints.append("Filename suggests this may be a BOMA measurement report.")
        if "abstract" in filename_lower:
            hints.append("Filename suggests this may be a lease abstract.")
        if "management" in filename_lower or "monthly" in filename_lower:
            hints.append("Filename suggests this may be a management report.")
        if "cam" in filename_lower or "reconciliation" in filename_lower:
            hints.append("Filename suggests this may be a CAM reconciliation.")
        if "financial" in filename_lower or "model" in filename_lower or "underwriting" in filename_lower:
            hints.append("Filename suggests this may be a financial model.")
        
        if mime_type:
            if "spreadsheet" in mime_type or "excel" in mime_type:
                hints.append("File is a spreadsheet (Excel format).")
            if "image" in mime_type:
                hints.append("File is an image - may be a screenshot of property records.")
        
        return " ".join(hints) if hints else ""
    
    async def extract_document(
        self, 
        text: str, 
        doc_type: str,
        doc_id: str,
        deal_name: str,
        filename: str
    ) -> dict[str, Any]:
        """
        Extract structured data from a document using the config-driven approach.
        This is the universal extraction function that replaces 9 separate agents.
        """
        config = self.configs.get(doc_type)
        
        if not config:
            return {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "deal_name": deal_name,
                "filename": filename,
                "extraction": {},
                "parse_error": f"No extraction config for doc_type: {doc_type}",
                "pipeline_stage": "extraction_failed",
                "extraction_timestamp": datetime.utcnow().isoformat()
            }
        
        # Build the extraction prompt
        fields_list = ", ".join(config["fields"])
        
        user_message = f"""Document Type: {doc_type}
Filename: {filename}

Extract these fields: {fields_list}

Document content:
{text[:50000]}  # Truncate to 50k chars as per tech ref

Return a JSON object with the extracted data."""

        response = await self.call_llm(
            system_prompt=config["system_prompt"],
            user_message=user_message,
            max_tokens=4000
        )
        
        try:
            extraction = json.loads(self._extract_json(response))
            
            # Apply enrichments based on doc type
            extraction = self._apply_enrichments(extraction, doc_type)
            
            return {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "deal_name": deal_name,
                "filename": filename,
                "extraction": extraction,
                "parse_error": None,
                "pipeline_stage": "extracted",
                "extraction_timestamp": datetime.utcnow().isoformat()
            }
        except json.JSONDecodeError as e:
            return {
                "doc_id": doc_id,
                "doc_type": doc_type,
                "deal_name": deal_name,
                "filename": filename,
                "extraction": {},
                "parse_error": f"JSON parse error: {str(e)}. Response: {response[:500]}",
                "pipeline_stage": "extraction_failed",
                "extraction_timestamp": datetime.utcnow().isoformat()
            }
    
    def _apply_enrichments(self, extraction: dict, doc_type: str) -> dict:
        """
        Apply post-extraction enrichments (like risk level calculation).
        This replaces the Lease Abstract Rent Roll node from n8n.
        Applied to ANY doc with lease_expiration_date, not just LEASE type.
        """
        # Look for expiration date in various formats
        expiry_date = None
        
        # Check various field names
        for field in ["lease_expiration_date", "lease_end", "expiry", "expiration"]:
            if field in extraction:
                value = extraction[field]
                if isinstance(value, dict):
                    value = value.get("value")
                if value:
                    expiry_date = self._parse_date(str(value))
                    break
        
        if expiry_date:
            # Calculate months remaining from TODAY (not report date - dynamic fix)
            today = datetime.now()
            delta = relativedelta(expiry_date, today)
            months_remaining = delta.years * 12 + delta.months
            
            # Assign risk level
            if months_remaining < 0:
                risk_level = "EXPIRED"
            elif months_remaining <= 3:
                risk_level = "CRITICAL"
            elif months_remaining <= 12:
                risk_level = "HIGH"
            elif months_remaining <= 24:
                risk_level = "MODERATE"
            else:
                risk_level = "LOW"
            
            extraction["_enriched"] = {
                "months_remaining": months_remaining,
                "risk_level": risk_level,
                "calculated_at": today.isoformat()
            }
        
        # Check for missing critical fields
        missing_fields = []
        critical_fields = {
            "LEASE": ["tenant_name", "rentable_sf", "lease_expiration_date", "base_rent_annual"],
            "RENT_ROLL": ["tenants", "summary"],
            "BOMA": ["suites", "building_totals"]
        }
        
        if doc_type in critical_fields:
            for field in critical_fields[doc_type]:
                value = extraction.get(field)
                if value is None or value == "" or (isinstance(value, dict) and not value.get("value")):
                    missing_fields.append(field)
        
        if missing_fields:
            extraction["_missing_fields"] = missing_fields
            extraction["_abstract_complete"] = False
        else:
            extraction["_abstract_complete"] = True
        
        return extraction
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse various date formats."""
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue
        
        return None
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from response, handling markdown fencing."""
        # Try to find JSON in markdown code blocks
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if json_match:
            return json_match.group(1).strip()
        
        # Try to find raw JSON
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json_match.group(0)
        
        return text
    
    async def batch_extract(
        self,
        documents: list[dict],
        deal_name: str
    ) -> list[dict]:
        """
        Process multiple documents in batch.
        This replaces the 9 parallel extraction lanes with a single loop.
        """
        results = []
        
        for doc in documents:
            # Classify if not already classified
            if "doc_type" not in doc or doc["doc_type"] == "UNKNOWN":
                classification = await self.classify_document(
                    doc["text"],
                    doc["filename"],
                    doc.get("mime_type")
                )
                doc["doc_type"] = classification["doc_type"]
                doc["classification_confidence"] = classification["confidence"]
            
            # Extract based on type
            extraction = await self.extract_document(
                text=doc["text"],
                doc_type=doc["doc_type"],
                doc_id=doc["doc_id"],
                deal_name=deal_name,
                filename=doc["filename"]
            )
            
            results.append(extraction)
        
        return results
