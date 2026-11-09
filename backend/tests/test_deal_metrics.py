from datetime import date

import pytest

from services.deal_metrics import (
    build_report, compute_metrics, months_until, names_match, norm_suite, num, parse_date, tier_for,
)
from tests.fixtures import AS_OF, BOA_LEASE, BOMA, extraction, full_package

TODAY = date.fromisoformat(AS_OF)


@pytest.fixture
def metrics():
    return compute_metrics(full_package(), as_of=TODAY)


@pytest.fixture
def report(metrics):
    return build_report(deal_id="d1", deal_name="Sterling Test", classified_documents=[],
                        extractions=full_package(), ingest_errors=[], metrics=metrics, synthesis=None,
                        pipeline_errors=[], files_uploaded=4, completed_at="2026-11-05T12:00:00Z")


def tenant(m, name):
    return next(t for t in m["tenants"] if t["name"] == name)


# ── parsing helpers ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("$104,029.20", 104029.20), ("10,508 SF", 10508), ("(5,260.34)", -5260.34),
    ({"value": 9.9, "confidence": 1}, 9.9), ("", None), (None, None), (True, None), ("n/a", None),
])
def test_num(raw, expected):
    assert num(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2028-06-30", date(2028, 6, 30)), ("06/30/2028", date(2028, 6, 30)),
    ("June 30, 2028", date(2028, 6, 30)), ("MTM", None), (None, None), ("2028-06-30T00:00:00", date(2028, 6, 30)),
])
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


def test_months_until_counts_partial_months_down():
    assert months_until(date(2028, 6, 30), TODAY) == 19
    assert months_until(date(2026, 5, 31), TODAY) == -6
    assert months_until(date(2026, 12, 4), TODAY) == 0


def test_name_and_suite_matching():
    assert names_match("Bank of America, National Association", "Bank of America")
    assert names_match("Complete Apartment Care", "Complete Apartment")
    assert not names_match("Apex Roofing", "Retrev Legal")
    assert norm_suite("Suite 200") == norm_suite("200") == norm_suite("Ste. 200") == "200"


# ── roster and reconciliation ────────────────────────────────────────────────

def test_rent_roll_comes_from_management_report_when_no_separate_rent_roll(metrics):
    assert metrics["has_rent_roll"]
    assert len(metrics["tenants"]) == 6
    assert metrics["occupied_rsf"] == 24847


def test_lease_and_boma_attach_to_the_right_tenants(metrics):
    boa = tenant(metrics, "Bank of America")
    assert boa["hasLease"] and boa["leaseRsf"] == 10508
    assert boa["bomaRsf"] == 10548.77
    assert tenant(metrics, "Complete Apartment Care")["bomaRsf"] == 2076.11  # matched by suite


def test_rsf_reconciliation_matches_the_bayou_numbers(metrics):
    rsf = metrics["rsf_reconciliation"]
    assert rsf["bomaTotalSF"] == 29451.52
    assert rsf["rentRollOccupiedSF"] == 24847
    assert rsf["deltaSF"] == pytest.approx(4604.52)
    assert rsf["deltaPercent"] == pytest.approx(18.53, abs=0.01)
    assert rsf["alertTriggered"]
    avg_psf = metrics["financial"]["totalAnnualRent"] / 24847
    assert rsf["baseRentRecovery"] == pytest.approx(4604.52 * avg_psf, abs=0.01)
    # Plus the CAM those feet should carry: August opex x 12, spread over the BOMA building.
    cam_psf = round(21881.36 * 12 / 29451.52, 2)
    assert rsf["camRatePSF"] == cam_psf
    assert rsf["camRecovery"] == pytest.approx(4604.52 * cam_psf, abs=0.01)
    assert rsf["estimatedAnnualRecovery"] == pytest.approx(rsf["baseRentRecovery"] + rsf["camRecovery"], abs=0.01)
    assert "3,389 SF of canopy/porch" in rsf["countyNote"]


def test_no_rsf_alert_without_a_second_source():
    m = compute_metrics([extraction("LEASE", "boa_lease.pdf", BOA_LEASE)], as_of=TODAY)
    assert not m["rsf_reconciliation"]["comparable"]
    assert not m["rsf_reconciliation"]["alertTriggered"]
    assert m["rsf_reconciliation"]["estimatedAnnualRecovery"] == 0


def test_expirations_risk_and_ar(metrics):
    assert tenant(metrics, "Doreen McClung")["monthsRemaining"] == -6
    assert tenant(metrics, "Bank of America")["riskLevel"] == "MEDIUM"
    retrev = tenant(metrics, "Retrev Legal")
    assert retrev["leaseExpiry"] is None and retrev["riskLevel"] == "HIGH"
    assert retrev["arStatus"] == "DELINQUENT" and retrev["arOver60"] == 18360.17
    assert tenant(metrics, "Apex Roofing")["arStatus"] == "CURRENT"  # prepaid credit is not delinquency
    assert metrics["financial"]["arDelinquency"] == 18360.17


def test_walt_is_rent_weighted_and_ignores_unknown_expiries(metrics):
    known = [t for t in metrics["tenants"] if t["monthsRemaining"] is not None]
    expected = sum(t["annualRent"] * max(t["monthsRemaining"], 0) for t in known) / sum(t["annualRent"] for t in known)
    assert metrics["walt_months"] == pytest.approx(expected, abs=0.1)
    assert metrics["walt_coverage_pct"] == pytest.approx(55.4, abs=0.1)


def test_noi_is_annualized_from_ytd_and_labelled(metrics):
    fin = metrics["financial"]
    assert fin["noi"] == pytest.approx(145995.52 * 12 / 8)
    assert "year-to-date" in fin["noiBasis"]
    assert fin["capRate"] is None  # no purchase price or model — not invented


def test_arithmetic_checks_use_stated_figures(metrics):
    checks = {c["label"]: c for c in metrics["arithmetic_checks"]}
    assert checks["Rent roll total RSF"]["status"] == "pass"
    assert checks["NOI (period)"]["status"] == "pass"
    assert checks["Bank reconciliation"]["status"] == "pass"
    assert checks["BOMA suites vs building total"]["status"] == "warning"


def test_arithmetic_check_catches_a_bad_total():
    bad = dict(BOMA, building_totals=dict(BOMA["building_totals"], total_rentable_sf=40000))
    m = compute_metrics([extraction("BOMA", "boma.xlsx", bad)], as_of=TODAY)
    check = next(c for c in m["arithmetic_checks"] if c["label"] == "BOMA suites vs building total")
    assert check["status"] == "fail"


def test_amendment_and_original_lease_merge_to_the_later_expiry():
    original = dict(BOA_LEASE, lease_expiration_date={"value": "2022-11-30", "confidence": 0.9})
    amendment = {"tenant_name": {"value": "Bank of America", "confidence": 0.9},
                 "lease_expiration_date": {"value": "2028-06-30", "confidence": 0.9}}
    m = compute_metrics([extraction("LEASE", "original.pdf", original),
                         extraction("LEASE", "amendment.pdf", amendment)], as_of=TODAY)
    assert len(m["leases"]) == 1
    assert m["leases"][0].end == date(2028, 6, 30)
    assert m["leases"][0].rsf == 10508  # filled from the original


def test_leases_alone_build_a_roster():
    m = compute_metrics([extraction("LEASE", "boa_lease.pdf", BOA_LEASE)], as_of=TODAY)
    assert [t["name"] for t in m["tenants"]] == ["Bank of America, National Association"]
    assert m["tenants"][0]["annualRent"] == 104029.20


def test_failed_extraction_is_reported_not_counted():
    bad = {"doc_id": "x", "doc_type": "LEASE", "filename": "scan.pdf", "extraction": {}, "parse_error": "boom"}
    m = compute_metrics(full_package() + [bad], as_of=TODAY)
    assert m["failed_extractions"][0]["filename"] == "scan.pdf"
    assert len(m["tenants"]) == 6


# ── score, flags, report ─────────────────────────────────────────────────────

def test_score_categories_add_up_and_have_reasons(report):
    cats = report["scoreBreakdown"]
    assert set(cats) == {"dataCompleteness", "rsfAlignment", "financialIntegrity",
                         "leaseLeverage", "riskProfile", "documentCoverage"}
    assert [c["max"] for c in cats.values()] == [20, 20, 20, 20, 15, 15]
    assert report["score"] == round(sum(c["points"] for c in cats.values()))
    assert all(c["reasons"] for c in cats.values())
    assert cats["dataCompleteness"]["points"] == 20
    assert cats["documentCoverage"]["points"] == 15  # full coverage + RSF intelligence bonus
    assert report["tier"] == tier_for(report["score"])[0]


def test_fewer_documents_score_lower_on_completeness():
    m = compute_metrics([extraction("LEASE", "boa_lease.pdf", BOA_LEASE)], as_of=TODAY)
    r = build_report(deal_id="d", deal_name="x", classified_documents=[], extractions=[], ingest_errors=[],
                     metrics=m, synthesis=None, pipeline_errors=[], files_uploaded=1, completed_at="t")
    assert r["scoreBreakdown"]["dataCompleteness"]["points"] == 4


@pytest.mark.parametrize("score,tier", [(85, "GREEN"), (80, "GREEN"), (66, "YELLOW"), (43.5, "ORANGE"), (10, "RED")])
def test_tiers(score, tier):
    assert tier_for(score)[0] == tier


def test_red_flags_cover_the_known_problems(report):
    cats = [f["category"] for f in report["redFlags"]]
    assert "RSF Discrepancy" in cats
    assert "Missing Expiry" in cats
    lapsed = next(f for f in report["redFlags"] if f["category"] == "Expired Since Report")
    assert lapsed["description"].startswith("2 lease(s) ran out after the 2025-08-20 report")
    assert "AR Delinquency" in cats
    assert cats.count("Suite Area Underbilled") == 1  # consolidated
    severities = [f["severity"] for f in report["redFlags"]]
    assert severities == sorted(severities, key=["HIGH", "MEDIUM", "LOW"].index)
    missing = next(f for f in report["redFlags"] if f["category"] == "Missing Expiry")
    assert "Retrev Legal (Suite 301)" in missing["description"]


def test_ai_review_flags_are_merged_and_labelled(metrics):
    synthesis = {"red_flags": [{"severity": "critical", "category": "Termination Right",
                                "description": "BoA can terminate on 6 months notice", "impact": "x"}],
                 "what_to_get_next": [{"document": "Tenant estoppels", "why_needed": "confirm terms"}],
                 "property_address": "5041 Bayou Blvd"}
    r = build_report(deal_id="d", deal_name="x", classified_documents=[], extractions=full_package(),
                     ingest_errors=[], metrics=metrics, synthesis=synthesis, pipeline_errors=[],
                     files_uploaded=4, completed_at="t")
    ai = [f for f in r["redFlags"] if f["source"] == "ai_review"]
    assert ai and ai[0]["severity"] == "HIGH"
    assert any("Tenant estoppels" in item for item in r["whatToGetNext"])
    first = r["whatToGetNext"][0]
    assert first.startswith("Leases for Retrev Legal, Apex Roofing")  # biggest dollar gaps first
    assert "(Retrev Legal also has no expiration on file)" in first


def test_report_has_every_field_the_dashboard_reads(report):
    for key in ("id", "dealName", "propertyAddress", "score", "tier", "dealReadiness", "subScores",
                "rsfReconciliation", "financialSummary", "walt", "redFlags", "whatToGetNext", "tenants",
                "leaseAbstracts", "documents", "arithmeticChecks", "expirySchedule"):
        assert key in report
    assert all(isinstance(item, str) for item in report["whatToGetNext"])
    abstract = report["leaseAbstracts"][0]
    assert abstract["expenseStructure"] == "NNN"
    assert abstract["expirationDate"] == "2028-06-30"
    schedule = {b["label"]: b["annualRent"] for b in report["expirySchedule"]}
    assert schedule["Unknown"] == 132000 and schedule["2028"] == 104029.20


def test_leases_without_rent_roll_compare_only_their_own_suites():
    # A single lease against a whole-building BOMA must not read as a building-wide gap.
    m = compute_metrics([extraction("LEASE", "boa_lease.pdf", BOA_LEASE),
                         extraction("BOMA", "boma.xlsx", BOMA)], as_of=TODAY)
    rsf = m["rsf_reconciliation"]
    assert rsf["bomaTotalSF"] == 10548.77 and rsf["rentRollOccupiedSF"] == 10508
    assert rsf["deltaPercent"] == pytest.approx(0.39, abs=0.01)
    assert not rsf["alertTriggered"]
    assert rsf["occupiedSource"] == "leases (1 suite)"
    assert m["financial"]["vacancy"] is None  # leases can't tell us what's vacant


def test_irrelevant_files_do_not_cost_coverage(metrics):
    classified = [{"doc_id": f"d{i}", "filename": f"f{i}", "doc_type": t, "page_count": 1}
                  for i, t in enumerate(["MANAGEMENT_REPORT", "LEASE", "BOMA", "COUNTY_PA", "OTHER"])]
    r = build_report(deal_id="d", deal_name="x", classified_documents=classified, extractions=full_package(),
                     ingest_errors=[], metrics=metrics, synthesis=None, pipeline_errors=[],
                     files_uploaded=5, completed_at="t")
    coverage = r["scoreBreakdown"]["documentCoverage"]
    assert coverage["reasons"][0]["text"] == "4 of 4 documents read and extracted"


def test_a_thin_package_does_not_outscore_the_full_one(report):
    m = compute_metrics([extraction("LEASE", "boa_lease.pdf", BOA_LEASE),
                         extraction("BOMA", "boma.xlsx", BOMA)], as_of=TODAY)
    thin = build_report(deal_id="d", deal_name="x", classified_documents=[], extractions=[], ingest_errors=[],
                        metrics=m, synthesis=None, pipeline_errors=[], files_uploaded=2, completed_at="t")
    assert thin["score"] < report["score"]
    assert thin["tier"] in ("ORANGE", "RED")
    fin_reasons = [r["text"] for r in thin["scoreBreakdown"]["financialIntegrity"]["reasons"]]
    assert "No receivables data — collections can't be verified" in fin_reasons
    assert thin["scoreBreakdown"]["rsfAlignment"]["points"] <= 10


# ── shopping-center package (Town & Country shape) ───────────────────────────

def _row(name, suite, rsf=None, monthly=None, end=None, status="Current", **extra):
    return {"tenant_name": name, "suite": suite, "rsf": rsf, "monthly_base_rent": monthly,
            "annual_base_rent": monthly * 12 if monthly else None, "lease_end": end, "status": status, **extra}


def _center(collection=None, report_date="2026-10-31", aged=False):
    ar = {"ar_balance": 900.0}
    if aged:
        ar.update(ar_over_60=0.0, ar_over_90=0.0)
    rows = [
        _row("Early Learning Coalition", "100", 4000, 8000, "2030-01-31", **ar),
        _row("Early Learning Coalition", "110", 3000, 6000, "2030-01-31"),
        _row("Nail Spa", "120", 1200, 2000, status="MTM"),
        _row("Mars Caribbean", "130", 1500, 2500),
        _row("BUILDING MAINTENANCE ROOM", "L8"),
        _row("BUILDING STORAGE ROOM", "L10", 275),
        _row("VACANT", "140", 2000, is_vacant=True),
    ]
    data = {"report_date": report_date, "rent_roll": rows}
    if collection:
        data["collection_summary"] = collection
    return compute_metrics([extraction("MANAGEMENT_REPORT", "tc.pdf", data)], as_of=TODAY)


def _flags(m):
    return build_report(deal_id="d", deal_name="TC", classified_documents=[], extractions=[], ingest_errors=[],
                        metrics=m, synthesis=None, pipeline_errors=[], files_uploaded=1,
                        completed_at="2026-11-05T12:00:00Z")


def test_landlord_rooms_are_not_tenants_or_vacancy():
    m = _center()
    names = [t["name"] for t in m["tenants"]]
    assert "BUILDING MAINTENANCE ROOM" not in names and "BUILDING STORAGE ROOM" not in names
    assert m["vacant_rsf"] == 2000
    assert {x["suite"] for x in m["landlord_use"]} == {"L8", "L10"}


def test_month_to_month_is_one_medium_flag_not_missing_expiry():
    r = _flags(_center())
    missing = [f for f in r["redFlags"] if f["category"] == "Missing Expiry"]
    assert [f["description"].split(" (")[0] for f in missing] == ["Mars Caribbean"]
    mtm = [f for f in r["redFlags"] if f["category"] == "Month-to-Month"]
    assert len(mtm) == 1 and mtm[0]["severity"] == "MEDIUM" and "Nail Spa" in mtm[0]["description"]
    assert not any("Nail Spa" in item for item in r["whatToGetNext"] if item.startswith("Executed lease"))


def test_tenant_in_two_suites_is_one_concentration_flag():
    r = _flags(_center())
    conc = [f for f in r["redFlags"] if f["category"] == "Tenant Concentration"]
    assert len(conc) == 1 and "2 suites" in conc[0]["description"]
    risk = r["scoreBreakdown"]["riskProfile"]["reasons"]
    assert any("Early Learning Coalition is 76%" in x["text"] for x in risk)


def test_unaged_balances_do_not_earn_full_ar_points():
    unaged = _flags(_center())["scoreBreakdown"]["financialIntegrity"]["reasons"]
    assert any("not aged" in x["text"] and x["points"] == 3 for x in unaged)
    aged = _flags(_center(aged=True))["scoreBreakdown"]["financialIntegrity"]["reasons"]
    assert any(x["text"] == "No 60+ day receivables" and x["points"] == 8 for x in aged)


def test_billed_rent_short_of_contract_is_flagged_as_billing_gap():
    m = _center(collection={"billed_minimum_rent": 15000})
    check = next(c for c in m["arithmetic_checks"] if c["label"] == "Contract rent vs billed rent")
    assert check["status"] == "fail" and "short $3,500" in check["detail"]
    flag = next(f for f in _flags(m)["redFlags"] if f["category"] == "Contract vs Billed Rent")
    assert "abatement" in flag["impact"]
    assert not any(f["category"] == "Arithmetic Mismatch" for f in _flags(m)["redFlags"])


def test_report_date_and_stale_data():
    fresh = _flags(_center())
    assert fresh["dataAsOf"] == "2026-10-31"
    assert not any(f["category"] == "Stale Data" for f in fresh["redFlags"])
    old = _flags(_center(report_date="2026-02-28"))
    assert old["dataAgeMonths"] >= 8
    assert any(f["category"] == "Stale Data" for f in old["redFlags"])


def test_leases_that_lapsed_after_the_report_are_grouped():
    m = _center(report_date="2026-02-28")
    m["tenants"][0]["leaseExpiry"], m["tenants"][0]["monthsRemaining"] = "2026-06-30", -5
    m["tenants"][1]["leaseExpiry"], m["tenants"][1]["monthsRemaining"] = "2026-06-30", -5
    flags = _flags(m)["redFlags"]
    lapsed = [f for f in flags if f["category"] == "Expired Since Report"]
    assert len(lapsed) == 1 and "Early Learning Coalition (2026-06-30)" in lapsed[0]["description"]
    assert not any(f["category"] == "Expired Lease" for f in flags)
