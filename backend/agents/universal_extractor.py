"""
Universal Extraction Agent

One config-driven extractor for every document type. It classifies a
document, then extracts it against that type's schema from
config/extraction_prompts.py. It does no arithmetic: every derived number
is computed in services/deal_metrics.py from what this agent extracts.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from .base import BaseAgent
from config.extraction_prompts import (
    EXTRACTION_CONFIGS,
    CLASSIFICATION_PROMPT,
    GROUNDING_RULES,
    DOC_TYPES,
)

# Fields a lease abstract can't do without. Missing ones are surfaced in the UI.
CRITICAL_LEASE_FIELDS = ["tenant_name", "rentable_sf", "lease_expiration_date", "base_rent_annual"]

CLASSIFY_SAMPLE_CHARS = 1500
EXTRACT_MAX_CHARS = 120_000


class UniversalExtractor(BaseAgent):
    def __init__(self):
        super().__init__(name="UniversalExtractor", system_prompt="")
        self.configs = EXTRACTION_CONFIGS

    async def classify_document(self, text: str, filename: str,
                                mime_type: Optional[str] = None) -> dict[str, Any]:
        """Classify from the first and last portions of the text plus filename hints."""
        user_message = (
            f"Filename: {filename}\n"
            f"{self._filename_hint(filename, mime_type)}\n\n"
            f"Document content (first and last portions):\n{self._sample(text)}\n\n"
            "Classify this document."
        )
        response = await self.call_llm(CLASSIFICATION_PROMPT, user_message, max_tokens=500)
        parsed = self._parse_json_response(response)
        doc_type = str(parsed.get("document_type", "")).upper().strip()
        if doc_type not in DOC_TYPES:
            doc_type = "OTHER"
        return {
            "doc_type": doc_type,
            "confidence": float(parsed.get("confidence") or 0.0),
            "reasoning": parsed.get("reasoning") or parsed.get("_parse_error", ""),
            "filename": filename,
        }

    async def extract_document(self, text: str, doc_type: str, doc_id: str,
                               deal_name: str, filename: str) -> dict[str, Any]:
        base = {
            "doc_id": doc_id,
            "doc_type": doc_type,
            "deal_name": deal_name,
            "filename": filename,
            "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        }
        config = self.configs.get(doc_type)
        if not config:
            return {**base, "extraction": {}, "pipeline_stage": "extraction_failed",
                    "parse_error": f"No extraction config for doc_type: {doc_type}"}

        truncated = len(text) > EXTRACT_MAX_CHARS
        user_message = (
            f"Document type: {doc_type}\n"
            f"Filename: {filename}\n\n"
            f"Return JSON matching this schema (types are described in the values):\n"
            f"{json.dumps(config['output_schema'], indent=2)}\n\n"
            f"Document content{' (truncated)' if truncated else ''}:\n"
            f"{text[:EXTRACT_MAX_CHARS]}"
        )
        response = await self.call_llm(
            system_prompt=config["system_prompt"] + "\n" + GROUNDING_RULES,
            user_message=user_message,
            max_tokens=config["max_tokens"],
        )
        extraction = self._parse_json_response(response)
        if "_parse_error" in extraction:
            return {**base, "extraction": {}, "pipeline_stage": "extraction_failed",
                    "parse_error": f"Could not parse extraction JSON: {extraction.get('_raw', '')[:300]}"}

        missing = self._missing_fields(extraction, doc_type)
        return {
            **base,
            "extraction": extraction,
            "parse_error": None,
            "pipeline_stage": "extracted",
            "missing_fields": missing,
            "abstract_complete": not missing,
            "truncated": truncated,
        }

    def _missing_fields(self, extraction: dict, doc_type: str) -> list[str]:
        if doc_type != "LEASE":
            return []
        missing = []
        for field in CRITICAL_LEASE_FIELDS:
            value = extraction.get(field)
            if isinstance(value, dict):
                value = value.get("value")
            if value in (None, "", []):
                missing.append(field)
        return missing

    def _sample(self, text: str) -> str:
        text = text.strip()
        if len(text) <= CLASSIFY_SAMPLE_CHARS * 2:
            return text
        return (f"{text[:CLASSIFY_SAMPLE_CHARS]}\n\n[... middle omitted ...]\n\n"
                f"{text[-CLASSIFY_SAMPLE_CHARS:]}")

    def _filename_hint(self, filename: str, mime_type: Optional[str]) -> str:
        name = filename.lower()
        hints = []
        if "lease" in name and "abstract" not in name:
            hints.append("Filename suggests a lease.")
        if "abstract" in name:
            hints.append("Filename suggests a lease abstract.")
        if "rent" in name and "roll" in name:
            hints.append("Filename suggests a rent roll.")
        if "boma" in name or "measurement" in name:
            hints.append("Filename suggests a BOMA measurement report.")
        if "management" in name or "monthly" in name:
            hints.append("Filename suggests a management report.")
        if "cam" in name or "reconciliation" in name:
            hints.append("Filename suggests a CAM reconciliation.")
        if any(k in name for k in ("model", "underwriting", "proforma", "pro forma")):
            hints.append("Filename suggests a financial model.")
        if any(k in name for k in ("appraiser", "parcel", "county", "tax")):
            hints.append("Filename suggests a county property appraiser record.")
        if mime_type and ("spreadsheet" in mime_type or "excel" in mime_type):
            hints.append("File is a spreadsheet.")
        if mime_type and mime_type.startswith("image/"):
            hints.append("File is an image (possibly a screenshot of a property record).")
        return " ".join(hints)
