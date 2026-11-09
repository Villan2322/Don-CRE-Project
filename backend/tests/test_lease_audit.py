"""Lease audit: area and CAM gaps per suite, and whether each lease lets the landlord fix them."""

from datetime import date

import pytest

from services.deal_metrics import build_report, compute_metrics
from services.lease_audit import remeasurement_call
from tests.fixtures import AS_OF, BOA_LEASE, BOMA, MANAGEMENT_REPORT, extraction, full_package, sourced

TODAY = date.fromisoformat(AS_OF)


def suite(m, name):
    return next(a for a in m["lease_audit"]["tenants"] if a["name"].startswith(name))


def report(extractions):
    m = compute_metrics(extractions, as_of=TODAY)
    return m, build_report(deal_id="d", deal_name="x", classified_documents=[], extractions=extractions,
                           ingest_errors=[], metrics=m, synthesis=None, pipeline_errors=[],
                           files_uploaded=len(extractions), completed_at="t")


# ── remeasurement calls ──────────────────────────────────────────────────────

def call(**kw):
    args = dict(has_lease=True, delta_sf=900, delta_pct=10.0, remeasurement=None, deemed_final=None, rsf_source=None)
    args.update(kw)
    return remeasurement_call(**args)["call"]


def test_remeasurement_calls():
    assert call(remeasurement="Landlord may remeasure the Premises and adjust Base Rent accordingly") == "STRONG"
    assert call(deemed_final="The Rentable Area is stipulated and shall not be subject to remeasurement") == "NONE"
    assert call(remeasurement="Rent adjusts on remeasurement only if the variance exceeds 15%") == "NONE"
    assert call(remeasurement="Rent adjusts on remeasurement only if the variance exceeds 3%") == "STRONG"
    assert call(rsf_source="10,508 rentable square feet (per ANSI/BOMA Z65.1-1996)") == "NEGOTIABLE"
    assert call(remeasurement="None") == "NEGOTIABLE"
    assert call(has_lease=False) == "NO_LEASE"
    assert call(delta_sf=-900, delta_pct=-10.0) == "OVERBILLED"
    assert call(delta_sf=40, delta_pct=0.4) == "MATCHES"


# ── Bayou package (Don's floor-plan-vs-rent-roll case) ───────────────────────

def test_each_suite_gap_in_square_feet_and_dollars():
    m = compute_metrics(full_package(), as_of=TODAY)
    apex = suite(m, "Apex")
    assert apex["billedRsf"] == 1425 and apex["bomaRsf"] == 2468.64
    assert apex["deltaSF"] == pytest.approx(1043.64)
    assert apex["billedLoadFactor"] == pytest.approx(1425 / 1893, abs=0.001)
    assert apex["bomaLoadFactor"] == pytest.approx(1.304, abs=0.001)
    psf = 1500 * 12 / 1425
    assert apex["baseRentGap"] == pytest.approx(1043.64 * psf, abs=0.5)
    cam_psf = 21881.36 * 12 / 29451.52
    assert apex["camGap"] == pytest.approx(1043.64 * cam_psf, abs=0.5)
    assert apex["billedCamBasis"].startswith("estimated")
    assert apex["leverage"]["call"] == "NO_LEASE"
    assert suite(m, "Bank of America")["leverage"]["call"] == "MATCHES"


def test_summary_rolls_up_underbilled_suites():
    s = compute_metrics(full_package(), as_of=TODAY)["lease_audit"]["summary"]
    assert s["suitesUnderbilled"] == 5 and s["suitesOverbilled"] == 0
    assert s["totalUpside"] == pytest.approx(s["baseRentUpside"] + s["camUpside"], abs=0.02)
    assert s["billedLoadFactor"] < s["bomaLoadFactor"] == 1.304
    assert "annualized" in s["expensePoolBasis"]


def test_underbilled_flag_states_dollars_and_leverage():
    _, r = report(full_package())
    flag = next(f for f in r["redFlags"] if f["category"] == "Suite Area Underbilled")
    assert flag["severity"] == "HIGH"
    assert "base rent +" in flag["impact"] and "no lease on file" in flag["impact"]
    assert "Last year's CAM reconciliation" in " ".join(r["whatToGetNext"])
    assert r["leaseAudit"]["available"]


# ── lease terms change the answer ────────────────────────────────────────────

def _retrev_lease(**terms):
    base = {"tenant_name": sourced("Retrev Legal"), "suite_number": sourced("301"),
            "rentable_sf": sourced(9874, 0.95, "9,874 rentable square feet"),
            "lease_expiration_date": sourced("2029-02-28")}
    base.update({k: sourced(v) for k, v in terms.items()})
    return extraction("LEASE", "retrev.pdf", base)


def test_gross_lease_only_loses_base_rent():
    m = compute_metrics(full_package() + [_retrev_lease(expense_structure="Full Service Gross")], as_of=TODAY)
    retrev = suite(m, "Retrev")
    assert retrev["camGap"] == 0 and retrev["baseRentGap"] > 0
    assert "Gross lease" in retrev["expenseNote"]


def test_lease_that_fixes_the_area_is_called_locked():
    lease = _retrev_lease(expense_structure="NNN",
                          area_deemed_final="The rentable area is deemed to be 9,874 square feet for all purposes")
    m, r = report(full_package() + [lease])
    retrev = suite(m, "Retrev")
    assert retrev["leverage"]["call"] == "NONE"
    assert "deemed" in retrev["leverage"]["clause"]
    summary = r["leaseAudit"]["summary"]
    assert summary["collectibleUpside"] is None  # Retrev is locked; the rest wait on leases
    assert summary["pendingUpside"] == pytest.approx(summary["totalUpside"] - retrev["totalGap"], abs=0.05)


def test_base_year_lease_is_marked_upper_bound():
    m = compute_metrics(full_package() + [_retrev_lease(expense_structure="Modified Gross", base_year="2019")],
                        as_of=TODAY)
    assert "Base year 2019" in suite(m, "Retrev")["expenseNote"]


def test_actual_billing_beats_estimates():
    rows = [dict(r) for r in MANAGEMENT_REPORT["rent_roll"]]
    rows[3] = dict(rows[3], monthly_cam_charges=900.0, pro_rata_share_pct=5.0)  # Apex
    mgmt = dict(MANAGEMENT_REPORT, rent_roll=rows)
    cam = {"reconciliation_year": "2024", "total_cam_expenses": 240000.0,
           "tenant_reconciliations": [{"tenant_name": "Retrev Legal", "pro_rata_share_pct": 33.5,
                                       "amount_billed": 80000.0}]}
    m = compute_metrics([extraction("MANAGEMENT_REPORT", "m.pdf", mgmt), extraction("BOMA", "b.xlsx", BOMA),
                         extraction("CAM_RECONCILIATION", "cam.pdf", cam)], as_of=TODAY)
    s = m["lease_audit"]["summary"]
    assert s["expensePool"] == 240000 and s["expensePoolBasis"] == "CAM reconciliation 2024"
    apex = suite(m, "Apex")
    assert apex["billedCam"] == 10800 and apex["billedCamBasis"].startswith("rent roll")
    assert apex["billedShare"] == 5.0 and apex["bomaShare"] == pytest.approx(2468.64 / 29451.52 * 100, abs=0.001)
    assert apex["camGap"] == pytest.approx(2468.64 * 240000 / 29451.52 - 10800, abs=1)
    retrev = suite(m, "Retrev")
    assert retrev["billedCam"] == 80000 and retrev["billedShareSource"] == "CAM reconciliation"


def test_overbilled_tenant_is_a_risk_not_upside():
    rows = [dict(r) for r in MANAGEMENT_REPORT["rent_roll"]]
    rows[4] = dict(rows[4], rsf=12000)  # BofA billed on more than BOMA's 10,549
    _, r = report([extraction("MANAGEMENT_REPORT", "m.pdf", dict(MANAGEMENT_REPORT, rent_roll=rows)),
                   extraction("BOMA", "b.xlsx", BOMA)])
    assert r["leaseAudit"]["summary"]["suitesOverbilled"] == 1
    assert r["leaseAudit"]["summary"]["overbilledExposure"] > 0
    assert any(f["category"] == "Tenant Overbilled" for f in r["redFlags"])


def test_no_boma_means_no_audit():
    m = compute_metrics([extraction("MANAGEMENT_REPORT", "m.pdf", MANAGEMENT_REPORT)], as_of=TODAY)
    assert not m["lease_audit"]["available"]


def test_upside_splits_correctable_from_waiting_on_leases():
    lease = _retrev_lease(expense_structure="NNN",
                          remeasurement_rights="Landlord may remeasure the Premises and adjust rent accordingly")
    s = compute_metrics(full_package() + [lease], as_of=TODAY)["lease_audit"]["summary"]
    retrev = suite(compute_metrics(full_package() + [lease], as_of=TODAY), "Retrev")
    assert retrev["leverage"]["call"] == "STRONG"
    assert s["collectibleUpside"] == retrev["totalGap"]
    assert s["collectibleUpside"] + s["pendingUpside"] == pytest.approx(s["totalUpside"], abs=0.05)


def test_share_is_only_shown_when_a_document_states_it():
    m = compute_metrics(full_package(), as_of=TODAY)
    assert suite(m, "Retrev")["billedShare"] is None
