"""
5041 Bayou Blvd test deal (the "Sterling Test" package).

Extraction outputs shaped exactly as the schemas in config/extraction_prompts.py
ask Claude to return them. The rent roll comes from the management report,
as it did in the original package.
"""

AS_OF = "2026-11-05"


def sourced(value, confidence=0.95, source_text=""):
    return {"value": value, "confidence": confidence, "source_text": source_text}


def rr_row(name, suite, rsf, start, end, monthly, **ar):
    return {
        "tenant_name": name, "suite": suite, "is_vacant": False, "rsf": rsf,
        "lease_start": start, "lease_end": end, "monthly_base_rent": monthly,
        "annual_base_rent": round(monthly * 12, 2), "rent_psf": round(monthly * 12 / rsf, 2),
        "monthly_cam_charges": None, "status": "Current",
        "ar_balance": ar.get("balance"), "ar_over_60": None, "ar_over_90": ar.get("over_90"),
    }


MANAGEMENT_REPORT = {
    "property_name": "Bayou Boulevard Investments LLC",
    "property_address": "5041 Bayou Blvd, Pensacola, FL 32503",
    "management_company": "Stirling Properties",
    "report_period": "August 2025",
    "report_date": "2025-08-20",
    "rent_roll": [
        rr_row("Doreen McClung", "Suite 100", 560, "2021-06-01", "2026-05-31", 700.00),
        rr_row("Feldmann Agency", "Suite 120", 780, "2022-02-01", "2027-01-31", 950.00),
        rr_row("Complete Apartment Care", "Suite 130", 1700, "2022-02-01", "2027-01-31", 1850.00),
        rr_row("Apex Roofing", "Suite 140", 1425, "2020-11-01", "2025-10-31", 1500.00),
        rr_row("Bank of America", "Suite 200", 10508, "2012-12-01", "2028-06-30", 8669.10),
        rr_row("Retrev Legal", "Suite 301", 9874, "2019-03-01", None, 11000.00),
    ],
    "rent_roll_summary": {
        "total_rsf": 24847, "occupied_rsf": 24847, "vacant_rsf": None, "occupancy_rate": 100,
        "total_monthly_rent": 24669.10, "total_annual_rent": None,
    },
    "income_period_to_date": {
        "period_label": "August 2025", "months_covered": 1, "base_rent": 23008.02,
        "total_revenue": 47209.18, "operating_expenses": 21881.36, "noi": 25327.82,
    },
    "income_year_to_date": {
        "period_label": "Jan-Aug 2025", "months_covered": 8, "base_rent": 183953.20,
        "total_revenue": None, "operating_expenses": None, "noi": 145995.52,
    },
    "occupancy_rate": 100,
    "cam_recovery_ratio_pct": 103.2,
    "bank_reconciliation": {"bank_balance": 60243.08, "gl_balance": 60243.08, "difference": 0},
    "ar_aging": [
        {"tenant_name": "Retrev Legal", "total_outstanding": 30268.31, "over_60_days": None,
         "over_90_days": 18360.17, "note": "Tenant only paying $15,000/month vs $20,349.83 owed"},
        {"tenant_name": "Apex Roofing", "total_outstanding": -5260.34, "over_60_days": None,
         "over_90_days": None, "note": "Prepaid credit"},
        {"tenant_name": "Feldmann Agency", "total_outstanding": -834.24, "over_60_days": None,
         "over_90_days": None, "note": "Prepaid credit"},
    ],
    "tenant_updates": [],
}

BOA_LEASE = {
    "tenant_name": sourced("Bank of America, National Association"),
    "landlord_name": sourced("Bayou Boulevard Investments LLC"),
    "premises_address": sourced("Suite 200, 5041 Bayou Boulevard, Pensacola, Florida 32503"),
    "suite_number": sourced("200"),
    "rentable_sf": sourced(10508, 0.98, "Net Rentable Area: 10,508 square feet"),
    "usable_sf": sourced(None, 0.0),
    "lease_commencement_date": sourced("2012-12-01"),
    "lease_expiration_date": sourced("2028-06-30", 0.97, "Expiration Date: June 30, 2028"),
    "base_rent_annual": sourced(104029.20, 0.97, "Annual Base Rent: $104,029.20"),
    "base_rent_monthly": sourced(8669.10),
    "rent_per_sf": sourced(9.90),
    "escalation_type": sourced(None, 0.0),
    "escalation_percentage": sourced(None, 0.0),
    "escalation_schedule": sourced(None, 0.0),
    "expense_structure": sourced("Net Lease - pro-rata share of operating expenses and taxes"),
    "cam_cap": sourced(None, 0.0),
    "renewal_options": sourced("One 5.5-year term, then six 5-year terms; 12 months' notice"),
    "remeasurement_rights": sourced(None, 0.0),
    "ti_allowance": sourced(None, 0.0),
    "security_deposit": sourced(None, 0.0),
}

BOMA = {
    "building_name": "5041 Bayou Blvd",
    "measurement_date": None,
    "measurement_standard": "ANSI/BOMA Z65.1-1996",
    "suites": [
        {"suite": "Suite 100", "tenant_name": "Doreen McClung", "usable_sf": 676, "rentable_sf": 881.56, "load_factor": 1.304},
        {"suite": "Suite 120", "tenant_name": "Feldmann Agency", "usable_sf": 841, "rentable_sf": 1096.74, "load_factor": 1.304},
        {"suite": "Suite 130", "tenant_name": "Complete Apartment", "usable_sf": 1592, "rentable_sf": 2076.11, "load_factor": 1.304},
        {"suite": "Suite 140", "tenant_name": "Apex Roofing", "usable_sf": 1893, "rentable_sf": 2468.64, "load_factor": 1.304},
        {"suite": "Suite 200", "tenant_name": "Bank of America", "usable_sf": 8089, "rentable_sf": 10548.77, "load_factor": 1.304},
        {"suite": "Suite 301", "tenant_name": "Retrev Legal", "usable_sf": 8558, "rentable_sf": 11160.38, "load_factor": 1.304},
    ],
    "building_totals": {
        "total_usable_sf": 22579, "total_rentable_sf": 29451.52, "building_load_factor": 1.304087869,
        "common_area_sf": 6866, "gross_building_area": None,
    },
}

COUNTY_PA = {
    "parcel_id": "61462", "property_address": "5041 BAYOU BLVD, PENSACOLA FL 32503",
    "owner_name": None, "year_built": 1975, "improvement_type": "BRNCH/MOTR BANK",
    "total_sf": 35857, "base_area_sf": 21670, "upper_story_sf": 10798, "canopy_sf": 3008, "porch_sf": 381,
    "land_value": None, "improvement_value": None, "total_assessed_value": None, "tax_amount": None,
}


def extraction(doc_type, filename, data, doc_id=None, missing=None):
    return {"doc_id": doc_id or f"doc-{filename}", "doc_type": doc_type, "filename": filename,
            "deal_name": "Sterling Test", "extraction": data, "parse_error": None,
            "pipeline_stage": "extracted", "missing_fields": missing or []}


def full_package():
    return [
        extraction("MANAGEMENT_REPORT", "stirling_aug_2025.pdf", MANAGEMENT_REPORT),
        extraction("LEASE", "boa_lease.pdf", BOA_LEASE),
        extraction("BOMA", "boma_measurements.xlsx", BOMA),
        extraction("COUNTY_PA", "escambia_pa.png", COUNTY_PA),
    ]


# Text versions of the files for end-to-end runs through the graph.
FILE_TEXT = {
    "stirling_aug_2025.txt": "STIRLING PROPERTIES Monthly Management Report August 2025 Bayou Boulevard Investments LLC " * 5,
    "boa_lease.txt": "LEASE AGREEMENT between Bayou Boulevard Investments LLC and Bank of America " * 5,
    "boma_measurements.csv": "Suite,Tenant,Usable SF,Rentable SF\nSuite 200,Bank of America,8089,10548.77\n" * 3,
    "escambia_pa.txt": "ESCAMBIA COUNTY PROPERTY APPRAISER Parcel 61462 5041 BAYOU BLVD " * 5,
    "site_photo_notes.txt": "Notes from the site walk. Parking lot needs restriping. " * 5,
}

CLASSIFY_BY_FILE = {
    "stirling_aug_2025.txt": "MANAGEMENT_REPORT",
    "boa_lease.txt": "LEASE",
    "boma_measurements.csv": "BOMA",
    "escambia_pa.txt": "COUNTY_PA",
    "site_photo_notes.txt": "OTHER",
}

EXTRACT_BY_TYPE = {
    "MANAGEMENT_REPORT": MANAGEMENT_REPORT,
    "LEASE": BOA_LEASE,
    "BOMA": BOMA,
    "COUNTY_PA": COUNTY_PA,
}

SYNTHESIS_RESPONSE = {
    "property_name": "Bayou Boulevard Investments LLC",
    "property_address": "5041 Bayou Blvd, Pensacola, FL 32503",
    "executive_summary": "Two-story office building at 5041 Bayou Blvd with six tenants.",
    "red_flags": [{
        "severity": "MEDIUM", "category": "Renewal Leverage",
        "description": "Bank of America holds seven renewal options at fixed notice",
        "impact": "Anchor controls term for decades", "resolution": "Review option rent terms",
        "source_documents": ["boa_lease.txt"],
    }],
    "what_to_get_next": [
        {"document": "Tenant estoppel certificates", "why_needed": "Confirms rent and term from each tenant", "priority": 1},
    ],
}
