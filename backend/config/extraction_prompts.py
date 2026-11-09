"""
Config-driven extraction prompts for every supported document type.

One UniversalExtractor reads this map instead of nine hand-built agents.
Each config's output_schema is sent to Claude with the document, so every
extraction comes back in a predictable shape that services/deal_metrics.py
can read without guessing field names.
"""

from typing import TypedDict


class ExtractionConfig(TypedDict):
    system_prompt: str
    output_schema: dict
    max_tokens: int


# Appended to every extraction system prompt. Grounding rules live here so
# they apply the same way to every document type.
GROUNDING_RULES = """
Rules:
- Return ONLY a JSON object matching the schema. No prose, no markdown fences.
- Use only what is printed in the document. Never estimate, infer, or calculate a value that is not stated.
- If a field is not in the document, set it to null. Do not drop the key.
- Numbers are plain JSON numbers: no $, commas, % signs, or units (10508, not "10,508 SF").
- Percentages are numbers on a 0-100 scale (3.5 for 3.5%).
- Dates are YYYY-MM-DD. If only month and year are given, use the first of the month.
- In tables, read each row on its own. If a cell is blank, return null for it — never copy a value
  from the row above or below, and never fill a blank from a total.
"""


def _sourced(value_type: str) -> dict:
    """A field that carries its own confidence and the text it came from."""
    return {
        "value": value_type,
        "confidence": "number 0-1",
        "source_text": "string — the exact words from the document, under 200 characters",
    }


LEASE_FIELDS = {
    "tenant_name": "string",
    "landlord_name": "string",
    "premises_address": "string",
    "suite_number": "string",
    "rentable_sf": "number",
    "usable_sf": "number",
    "lease_commencement_date": "string (YYYY-MM-DD)",
    "lease_expiration_date": "string (YYYY-MM-DD)",
    "base_rent_annual": "number — current annual base rent",
    "base_rent_monthly": "number — current monthly base rent",
    "rent_per_sf": "number — current annual base rent per rentable SF",
    "escalation_type": "string (fixed %, CPI, fixed $ steps, none)",
    "escalation_percentage": "number",
    "escalation_schedule": "string",
    "expense_structure": "string (NNN, Modified Gross, Full Service Gross, Net, etc.)",
    "cam_cap": "string",
    "pro_rata_share_pct": "number (0-100) — tenant's share of building expenses, only if the lease states it",
    "pro_rata_share_basis": "string — how the share is defined, e.g. 'premises RSF / building RSF of 29,452'",
    "recoverable_expenses": "string — what the tenant pays a share of (CAM, taxes, insurance, utilities, ...)",
    "expense_exclusions": "string — expenses the lease says the tenant does NOT pay for",
    "admin_fee": "string — management or administrative fee the landlord may add, and any cap",
    "gross_up": "string — gross-up clause and its occupancy threshold",
    "base_year": "string — base year or expense stop, if the tenant only pays increases",
    "renewal_options": "string",
    "expansion_rights": "string",
    "remeasurement_rights": "string — any right to remeasure the premises and adjust rent or the "
                            "tenant's share, including any tolerance (e.g. 'only if more than 3% off')",
    "area_deemed_final": "string — exact words saying the stated area is deemed correct, stipulated, "
                         "or not subject to remeasurement; null if the lease says nothing like that",
    "right_of_first_refusal": "string",
    "ti_allowance": "number — total dollars",
    "ti_allowance_per_sf": "number",
    "security_deposit": "number",
    "guarantor": "string",
    "permitted_use": "string",
    "assignment_subletting_rights": "string",
    "early_termination_rights": "string",
    "co_tenancy_clause": "string",
    "exclusivity_clause": "string",
    "parking_spaces": "number",
    "signage_rights": "string",
}

RENT_ROLL_TENANT = {
    "tenant_name": "string (use 'VACANT' for vacant suites)",
    "suite": "string",
    "is_vacant": "boolean",
    "is_landlord_use": "boolean — true for space the landlord keeps (maintenance room, storage room, "
                       "management or leasing office) that is not leased to a tenant",
    "rsf": "number",
    "lease_start": "string (YYYY-MM-DD)",
    "lease_end": "string (YYYY-MM-DD) or null if blank / month-to-month",
    "monthly_base_rent": "number",
    "annual_base_rent": "number",
    "rent_psf": "number — annual base rent per SF as printed",
    "monthly_cam_charges": "number — CAM / operating expense recovery billed per month",
    "pro_rata_share_pct": "number (0-100), if printed",
    "status": "string as printed (Current, MTM, Expired, ...)",
    "ar_balance": "number — total outstanding; negative means prepaid credit",
    "ar_over_60": "number — amount 60+ days past due",
    "ar_over_90": "number — amount 90+ days past due",
}

RENT_ROLL_SCHEMA = {
    "property_name": "string",
    "as_of_date": "string (YYYY-MM-DD)",
    "tenants": [RENT_ROLL_TENANT],
    "summary": {
        "total_rsf": "number — stated total building/rentable SF, if printed",
        "occupied_rsf": "number — stated occupied SF, if printed",
        "vacant_rsf": "number — stated vacant SF, if printed",
        "occupancy_rate": "number (0-100), if printed",
        "total_monthly_rent": "number, if printed",
        "total_annual_rent": "number, if printed",
    },
}

INCOME_PERIOD = {
    "period_label": "string (e.g. 'August 2025' or 'Jan-Aug 2025')",
    "months_covered": "number — how many months this column covers",
    "base_rent": "number",
    "total_revenue": "number — total operating revenue / effective gross income",
    "operating_expenses": "number",
    "noi": "number",
}

EXTRACTION_CONFIGS: dict[str, ExtractionConfig] = {
    "LEASE": {
        "system_prompt": "You are a commercial real estate lease abstraction expert. "
                         "Extract the key terms of this lease, amendment, or extension with high precision. "
                         "Every field is an object with value, confidence, and source_text.",
        "output_schema": {field: _sourced(t) for field, t in LEASE_FIELDS.items()},
        "max_tokens": 8000,
    },

    "LEASE_ABSTRACT": {
        "system_prompt": "You are reviewing a lease abstract: a summary of one or more leases. "
                         "Extract one entry per lease summarized.",
        "output_schema": {
            "leases": [{
                "tenant_name": "string",
                "suite": "string",
                "rsf": "number",
                "lease_start": "string (YYYY-MM-DD)",
                "lease_end": "string (YYYY-MM-DD)",
                "annual_base_rent": "number",
                "rent_psf": "number",
                "escalations": "string",
                "expense_structure": "string",
                "renewal_options": "string",
                "notes": "string",
            }]
        },
        "max_tokens": 8000,
    },

    "RENT_ROLL": {
        "system_prompt": "You are a commercial real estate rent roll analyst. "
                         "Extract every row of the tenant roster, including vacant suites. "
                         "Copy the stated totals exactly as printed; do not compute them.",
        "output_schema": RENT_ROLL_SCHEMA,
        "max_tokens": 32000,
    },

    "BOMA": {
        "system_prompt": "You are a BOMA measurement analyst. Extract usable and rentable square footage "
                         "per suite and the building totals from this measurement report, spreadsheet, "
                         "or architectural area tabulation.",
        "output_schema": {
            "building_name": "string",
            "measurement_date": "string (YYYY-MM-DD)",
            "measurement_standard": "string (e.g. ANSI/BOMA Z65.1-2017)",
            "suites": [{
                "suite": "string",
                "tenant_name": "string",
                "floor": "string",
                "usable_sf": "number",
                "rentable_sf": "number",
                "load_factor": "number",
            }],
            "building_totals": {
                "total_usable_sf": "number",
                "total_rentable_sf": "number",
                "building_load_factor": "number",
                "common_area_sf": "number",
                "gross_building_area": "number",
            },
        },
        "max_tokens": 8000,
    },

    "FINANCIAL_MODEL": {
        "system_prompt": "You are a commercial real estate financial analyst. "
                         "Extract the underwriting assumptions and projections from this model.",
        "output_schema": {
            "property_name": "string",
            "acquisition_price": "number",
            "price_psf": "number",
            "cap_rate_going_in": "number (0-100)",
            "cap_rate_exit": "number (0-100)",
            "hold_period_years": "number",
            "noi_year_1": "number",
            "noi_stabilized": "number",
            "irr_levered": "number (0-100)",
            "irr_unlevered": "number (0-100)",
            "equity_multiple": "number",
            "debt_assumptions": "string",
            "rent_growth_assumptions": "string",
        },
        "max_tokens": 6000,
    },

    "CAM_RECONCILIATION": {
        "system_prompt": "You are analyzing a CAM (common area maintenance) reconciliation statement. "
                         "Extract actual vs budgeted expenses and each tenant's reconciliation.",
        "output_schema": {
            "reconciliation_year": "string",
            "total_cam_expenses": "number",
            "budgeted_cam": "number",
            "variance": "number",
            "tenant_reconciliations": [{
                "tenant_name": "string",
                "pro_rata_share_pct": "number (0-100)",
                "sf_used_for_share": "number",
                "amount_billed": "number",
                "amount_due": "number",
                "balance": "number",
            }],
            "expense_categories": [{"category": "string", "amount": "number"}],
        },
        "max_tokens": 8000,
    },

    "MANAGEMENT_REPORT": {
        "system_prompt": "You are analyzing a monthly or quarterly property management report package. "
                         "These often bundle a rent roll, receivables aging, income statement, and bank "
                         "reconciliation. Extract each section that is present.",
        "output_schema": {
            "property_name": "string",
            "property_address": "string",
            "management_company": "string",
            "report_period": "string",
            "report_date": "string (YYYY-MM-DD)",
            "rent_roll": [RENT_ROLL_TENANT],
            "rent_roll_summary": RENT_ROLL_SCHEMA["summary"],
            "income_period_to_date": INCOME_PERIOD,
            "income_year_to_date": INCOME_PERIOD,
            "occupancy_rate": "number (0-100)",
            "cam_recovery_ratio_pct": "number (0-100+)",
            "bank_reconciliation": {
                "bank_balance": "number",
                "gl_balance": "number",
                "difference": "number",
            },
            "ar_aging": [{
                "tenant_name": "string",
                "total_outstanding": "number — negative means prepaid credit",
                "over_60_days": "number",
                "over_90_days": "number",
                "note": "string",
            }],
            "collection_summary": {
                "billed_minimum_rent": "number — total base/minimum rent billed this period, from the "
                                       "billing or collection report",
                "total_billed": "number — all charges billed this period",
                "total_collected": "number — total paid this period",
                "total_unpaid": "number — total still owed",
            },
            "tenant_updates": ["string"],
        },
        "max_tokens": 32000,
    },

    "COUNTY_PA": {
        "system_prompt": "You are extracting data from a county property appraiser record or screenshot. "
                         "It holds official building areas, parcel data, and assessed values.",
        "output_schema": {
            "parcel_id": "string",
            "property_address": "string",
            "owner_name": "string",
            "year_built": "number",
            "improvement_type": "string",
            "total_sf": "number",
            "base_area_sf": "number",
            "upper_story_sf": "number",
            "canopy_sf": "number",
            "porch_sf": "number",
            "land_value": "number",
            "improvement_value": "number",
            "total_assessed_value": "number",
            "tax_amount": "number",
        },
        "max_tokens": 4000,
    },
}

# Spreadsheet rent rolls use the same extraction as PDF rent rolls.
EXTRACTION_CONFIGS["RENT_ROLL_XLSX"] = EXTRACTION_CONFIGS["RENT_ROLL"]

DOC_TYPES = list(EXTRACTION_CONFIGS.keys())


CLASSIFICATION_PROMPT = """You are a commercial real estate document classifier.
Classify the document into exactly ONE of these types:

- LEASE: an executed lease, lease amendment, or extension between landlord and tenant
- LEASE_ABSTRACT: a summary of lease terms (not the full lease)
- RENT_ROLL: a tenant roster with suites, square footage, and rents (PDF or text)
- RENT_ROLL_XLSX: a rent roll exported from a spreadsheet
- BOMA: a BOMA measurement report, area spreadsheet, or architectural lease outline drawing with area tabulations
- FINANCIAL_MODEL: an underwriting model with cap rates, IRR, or projections
- CAM_RECONCILIATION: a common area maintenance expense reconciliation
- MANAGEMENT_REPORT: a property management report package (often bundles rent roll, AR aging, income statement)
- COUNTY_PA: a county property appraiser record or tax record
- OTHER: anything that is none of the above

Return JSON only:
{"document_type": "TYPE", "confidence": 0.0-1.0, "reasoning": "one or two sentences"}
"""


SYNTHESIS_PROMPT = """You are a commercial real estate due diligence analyst reviewing a deal package for a buyer.

You receive two things:
1. COMPUTED METRICS — figures calculated in code from the documents (RSF totals, rents, WALT, AR, variances).
   Treat these as ground truth. Do not recalculate or contradict them.
2. EXTRACTIONS — the structured data pulled from each document.

Your job is the judgment the code cannot make:
- Lease-level risks: unusual termination, assignment, co-tenancy, or remeasurement rights; below-market rent;
  missing renewal options for major tenants; guarantor gaps.
- Conflicts between documents that the metrics do not already cover (names, dates, expense structures).
- What a buyer should request next, and why.

Do NOT raise flags for these — the code already flags them: RSF variance between rent roll and BOMA,
expired or expiring leases, tenants with no expiration date, AR delinquency, tenant concentration, and
arithmetic mismatches. Do not invent numbers. Every flag must point to something in the extractions.

Return JSON only:
{
  "property_name": "string or null",
  "property_address": "string or null — full street address if any document states it",
  "executive_summary": "2-4 plain sentences a buyer can read in 20 seconds",
  "red_flags": [
    {
      "severity": "HIGH | MEDIUM | LOW",
      "category": "short label, e.g. 'Termination Right'",
      "description": "what is wrong, naming the tenant/suite",
      "impact": "why it matters to the buyer",
      "resolution": "what to do about it",
      "source_documents": ["filename"]
    }
  ],
  "what_to_get_next": [
    {"document": "what to request", "why_needed": "one sentence", "priority": 1}
  ]
}
"""
