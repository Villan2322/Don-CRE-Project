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
    assert rsf["estimatedAnnualRecovery"] == pytest.approx(4604.52 * avg_psf, abs=0.01)
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
    assert cats.count("Expired Lease") == 2
    assert "AR Delinquency" in cats
    assert cats.count("Suite RSF Variance") == 1  # consolidated
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
    assert r["whatToGetNext"][0].startswith("Executed lease for Retrev Legal")


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
