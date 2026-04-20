"""
Config-driven extraction prompts for all document types.
This replaces 9 separate extraction agents with a single config map.
"""

from typing import TypedDict

class ExtractionConfig(TypedDict):
    system_prompt: str
    fields: list[str]
    output_schema: dict


# The 9 document types and their extraction configurations
EXTRACTION_CONFIGS: dict[str, ExtractionConfig] = {
    "LEASE": {
        "system_prompt": """You are a commercial real estate lease abstraction expert.
Extract all key terms from the lease document with high precision.
Return ONLY valid JSON matching the schema. Include confidence scores (0-1) for each field.""",
        "fields": [
            "tenant_name", "landlord_name", "premises_address", "suite_number",
            "rentable_sf", "usable_sf", "lease_commencement_date", "lease_expiration_date",
            "base_rent_annual", "base_rent_monthly", "rent_per_sf",
            "escalation_type", "escalation_percentage", "escalation_schedule",
            "expense_structure", "cam_cap", "cam_cap_type",
            "renewal_options", "renewal_terms", "expansion_rights",
            "remeasurement_rights", "right_of_first_refusal",
            "ti_allowance", "ti_allowance_per_sf",
            "security_deposit", "guarantor", "permitted_use",
            "assignment_subletting_rights", "early_termination_rights",
            "co_tenancy_clause", "exclusivity_clause",
            "parking_spaces", "parking_ratio", "signage_rights"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "tenant_name": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "landlord_name": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "premises_address": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "suite_number": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "rentable_sf": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "usable_sf": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "lease_commencement_date": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "lease_expiration_date": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "base_rent_annual": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "base_rent_monthly": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "rent_per_sf": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "escalation_type": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "escalation_percentage": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "cam_cap": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "renewal_options": {"type": "object", "properties": {"value": {"type": "string"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "ti_allowance": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}},
                "security_deposit": {"type": "object", "properties": {"value": {"type": "number"}, "confidence": {"type": "number"}, "source_text": {"type": "string"}}}
            }
        }
    },
    
    "LEASE_ABSTRACT": {
        "system_prompt": """You are reviewing a lease abstract summary document.
Extract all pre-summarized lease terms. This is typically a condensed version of a full lease.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "tenant_name", "suite", "rsf", "lease_start", "lease_end",
            "current_rent", "rent_psf", "escalations", "options",
            "expense_stop", "parking", "notes"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "tenant_name": {"type": "string"},
                "suite": {"type": "string"},
                "rsf": {"type": "number"},
                "lease_start": {"type": "string"},
                "lease_end": {"type": "string"},
                "current_rent": {"type": "number"},
                "rent_psf": {"type": "number"},
                "escalations": {"type": "string"},
                "options": {"type": "string"}
            }
        }
    },
    
    "RENT_ROLL": {
        "system_prompt": """You are a commercial real estate rent roll analyst.
Extract the complete tenant roster with all financial data.
Calculate totals and identify any arithmetic errors.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "tenants", "building_totals", "vacancy_summary", "collection_status"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "tenants": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tenant_name": {"type": "string"},
                            "suite": {"type": "string"},
                            "rsf": {"type": "number"},
                            "usf": {"type": "number"},
                            "lease_start": {"type": "string"},
                            "lease_end": {"type": "string"},
                            "monthly_base_rent": {"type": "number"},
                            "annual_base_rent": {"type": "number"},
                            "rent_psf": {"type": "number"},
                            "cam_charges": {"type": "number"},
                            "total_monthly": {"type": "number"},
                            "status": {"type": "string"},
                            "ar_balance": {"type": "number"}
                        }
                    }
                },
                "summary": {
                    "type": "object",
                    "properties": {
                        "total_rsf": {"type": "number"},
                        "occupied_rsf": {"type": "number"},
                        "vacant_rsf": {"type": "number"},
                        "occupancy_rate": {"type": "number"},
                        "total_monthly_rent": {"type": "number"},
                        "total_annual_rent": {"type": "number"},
                        "average_rent_psf": {"type": "number"},
                        "total_ar_outstanding": {"type": "number"}
                    }
                },
                "arithmetic_checks": {
                    "type": "object",
                    "properties": {
                        "sum_of_tenant_rsf_matches_total": {"type": "boolean"},
                        "sum_of_rents_matches_total": {"type": "boolean"},
                        "calculated_occupancy_matches_stated": {"type": "boolean"}
                    }
                }
            }
        }
    },
    
    "RENT_ROLL_XLSX": {
        "system_prompt": """You are analyzing a rent roll spreadsheet.
This is tabular data from an Excel file. Parse all rows carefully.
Return ONLY valid JSON matching the schema.""",
        "fields": ["tenants", "summary", "arithmetic_checks"],
        "output_schema": {
            "type": "object",
            "properties": {
                "tenants": {"type": "array"},
                "summary": {"type": "object"},
                "arithmetic_checks": {"type": "object"}
            }
        }
    },
    
    "BOMA": {
        "system_prompt": """You are a BOMA measurement report analyst.
Extract rentable and usable square footage per suite from the BOMA measurement certificate.
BOMA measurements are the official building measurements.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "building_name", "measurement_date", "measurement_standard",
            "suites", "building_totals"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "building_name": {"type": "string"},
                "measurement_date": {"type": "string"},
                "measurement_standard": {"type": "string"},
                "suites": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "suite": {"type": "string"},
                            "tenant_name": {"type": "string"},
                            "usable_sf": {"type": "number"},
                            "rentable_sf": {"type": "number"},
                            "load_factor": {"type": "number"},
                            "floor": {"type": "string"}
                        }
                    }
                },
                "building_totals": {
                    "type": "object",
                    "properties": {
                        "total_usable_sf": {"type": "number"},
                        "total_rentable_sf": {"type": "number"},
                        "building_load_factor": {"type": "number"},
                        "gross_building_area": {"type": "number"}
                    }
                }
            }
        }
    },
    
    "FINANCIAL_MODEL": {
        "system_prompt": """You are a commercial real estate financial analyst.
Extract key underwriting assumptions and projections from this financial model.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "property_name", "acquisition_price", "price_psf",
            "cap_rate_going_in", "cap_rate_exit", "hold_period",
            "noi_year_1", "noi_stabilized", "irr_levered", "irr_unlevered",
            "equity_multiple", "debt_assumptions", "rent_growth_assumptions"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "acquisition_price": {"type": "number"},
                "price_psf": {"type": "number"},
                "cap_rate_going_in": {"type": "number"},
                "noi_year_1": {"type": "number"},
                "irr_levered": {"type": "number"},
                "equity_multiple": {"type": "number"}
            }
        }
    },
    
    "CAM_RECONCILIATION": {
        "system_prompt": """You are analyzing a CAM (Common Area Maintenance) reconciliation statement.
Extract actual vs budgeted expenses, tenant share calculations, and reconciliation amounts.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "reconciliation_year", "total_cam_expenses", "budgeted_cam",
            "variance", "tenant_reconciliations", "expense_categories"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "reconciliation_year": {"type": "string"},
                "total_cam_expenses": {"type": "number"},
                "budgeted_cam": {"type": "number"},
                "variance": {"type": "number"},
                "tenant_reconciliations": {"type": "array"}
            }
        }
    },
    
    "MANAGEMENT_REPORT": {
        "system_prompt": """You are analyzing a property management report.
Extract operational metrics, income/expense data, and tenant updates.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "report_period", "property_name", "gross_potential_rent",
            "vacancy_loss", "effective_gross_income", "operating_expenses",
            "noi", "debt_service", "cash_flow", "occupancy_rate",
            "collections_summary", "ar_aging", "tenant_updates", "capital_projects"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "report_period": {"type": "string"},
                "property_name": {"type": "string"},
                "gross_potential_rent": {"type": "number"},
                "vacancy_loss": {"type": "number"},
                "effective_gross_income": {"type": "number"},
                "operating_expenses": {"type": "number"},
                "noi": {"type": "number"},
                "occupancy_rate": {"type": "number"},
                "ar_aging": {"type": "object"},
                "tenant_updates": {"type": "array"}
            }
        }
    },
    
    "COUNTY_PA": {
        "system_prompt": """You are extracting data from a County Property Appraiser record or screenshot.
This contains official building measurements, parcel data, and tax information.
Return ONLY valid JSON matching the schema.""",
        "fields": [
            "parcel_id", "property_address", "owner_name",
            "year_built", "improvement_type", "total_sf",
            "base_area_sf", "upper_story_sf", "canopy_sf", "porch_sf",
            "land_value", "improvement_value", "total_assessed_value",
            "tax_amount", "exemptions"
        ],
        "output_schema": {
            "type": "object",
            "properties": {
                "parcel_id": {"type": "string"},
                "property_address": {"type": "string"},
                "year_built": {"type": "number"},
                "total_sf": {"type": "number"},
                "base_area_sf": {"type": "number"},
                "upper_story_sf": {"type": "number"},
                "canopy_sf": {"type": "number"},
                "total_assessed_value": {"type": "number"}
            }
        }
    }
}


# Classification prompt - used to determine doc_type
CLASSIFICATION_PROMPT = """You are a commercial real estate document classifier.
Analyze the document content and classify it into ONE of these categories:

1. LEASE - A full executed lease agreement between landlord and tenant
2. LEASE_ABSTRACT - A summary or abstract of lease terms (not the full lease)
3. RENT_ROLL - A listing of tenants with rents and lease terms
4. RENT_ROLL_XLSX - Same as rent roll but from spreadsheet format
5. BOMA - Building measurement report following BOMA standards
6. FINANCIAL_MODEL - Underwriting model with IRR, cap rates, projections
7. CAM_RECONCILIATION - Common area maintenance expense reconciliation
8. MANAGEMENT_REPORT - Property management monthly/quarterly report
9. COUNTY_PA - County property appraiser record or tax document

Return JSON with:
{
    "document_type": "TYPE",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of why this classification"
}
"""


# Synthesis prompt - combines all extractions into deal analysis
SYNTHESIS_PROMPT = """You are a commercial real estate deal analyst synthesizing data from multiple documents.

You have been provided extractions from: {doc_types_present}

Your task:
1. Cross-reference data across all documents
2. Identify discrepancies (especially RSF between rent roll, leases, and BOMA)
3. Calculate key metrics: NOI, WALT, occupancy, concentration
4. Flag risks and red flags
5. Score the deal from 0-100

SCORING RUBRIC:
- Document Completeness (20 pts): All critical docs present?
- Data Consistency (25 pts): RSF, rent, dates match across sources?
- Lease Quality (20 pts): WALT, rollover concentration, tenant credit
- Financial Health (20 pts): Collections, AR aging, expense ratios
- Risk Factors (15 pts): Deduct for each red flag found

Return JSON with:
{
    "rsf_reconciliation": {
        "sources": {"RENT_ROLL": X, "LEASE_TOTAL": Y, "BOMA": Z},
        "variance_rent_roll_vs_boma": X,
        "variance_percentage": X.X,
        "by_tenant": [{"tenant": "...", "rent_roll_rsf": X, "boma_rsf": Y, "delta": Z}]
    },
    "rent_verification": {
        "total_annual_rent": X,
        "tenant_shares": [{"tenant": "...", "share_pct": X}],
        "concentration_flag": true/false
    },
    "lease_audit": {
        "walt_months": X,
        "lease_expiry_schedule": [{"tenant": "...", "expiry": "...", "months_remaining": X, "risk_level": "..."}]
    },
    "financial_summary": {
        "noi": X,
        "occupancy_pct": X,
        "ar_concerns": "...",
        "cam_recovery_ratio": X
    },
    "deal_score": {
        "overall_score": 0-100,
        "tier": "Verified/Standard/Under Review",
        "sub_scores": {
            "document_completeness": X,
            "data_consistency": X,
            "lease_quality": X,
            "financial_health": X,
            "risk_factors": X
        }
    },
    "red_flags": [
        {"severity": "CRITICAL/HIGH/MEDIUM/LOW", "flag": "...", "impact": "...", "resolution": "..."}
    ],
    "what_to_get_next": [
        {"document": "...", "why_needed": "...", "score_impact": X, "priority": 1}
    ],
    "rsf_recovery_opportunity": {
        "recoverable_sf": X,
        "estimated_annual_recovery": X,
        "alert_message": "..."
    }
}
"""


# Verification prompt - independent check of extracted values
VERIFICATION_PROMPT = """You are an independent verification agent.
You will be shown extracted values with their source text citations.
For each field, verify whether the extracted value accurately matches the source text.

Return for each field:
- VERIFIED: Value exactly matches source text
- PARTIAL: Value partially matches or requires interpretation
- UNVERIFIED: Cannot confirm value from source text
- BLOCKED: Source text is redacted, illegible, or missing

Do NOT use any external knowledge. Only verify against the provided source_text.
"""
