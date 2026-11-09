"""
Lease audit: is each tenant paying for the area it actually occupies?

Compares, suite by suite, the area each tenant is billed on (rent roll or
lease) to the BOMA measurement, and turns the gap into dollars:

    base rent gap = (BOMA RSF - billed RSF) x tenant's rent per SF
    CAM gap       = what the tenant should pay  - what it is billed
                  = expense pool x BOMA share   - billed CAM

The expense pool comes from a CAM reconciliation when there is one, otherwise
from the management report's operating expenses, annualized. Each lease's own
terms decide whether expenses pass through at all (a gross lease recovers
nothing; a base-year lease only recovers increases).

Then it reads each lease's remeasurement language and makes a call on whether
the landlord can actually correct the area:

    STRONG      the lease lets the landlord remeasure and adjust
    NEGOTIABLE  the lease is silent, or cites a BOMA standard it doesn't meet
    NONE        the lease fixes the area ("deemed", "stipulated") or the gap is
                inside the lease's own tolerance
    NO_LEASE    no lease in the package, so nobody can tell yet
    OVERBILLED  the tenant is billed on MORE than was measured: a claim risk
    MATCHES     billed area is within 2% of BOMA

Everything here is arithmetic on extracted values. No model calls.
"""

from __future__ import annotations

import re
from typing import Any, Optional

MATERIAL_PCT = 2.0  # below this, billed area "matches" BOMA

_FIXED_AREA = re.compile(
    r"deemed|conclusive|stipulat|agreed (upon|to be)|not (be )?subject to (re-?)?measure|"
    r"shall not be (adjusted|re-?measured|recalculated)|regardless of (the )?(actual|any) measure|"
    r"for all purposes", re.I)
_REMEASURE = re.compile(r"re-?measur|recalculat|re-?comput|adjust\w*\b.{0,60}\b(rent|area|share|square)", re.I)
_NO_RIGHT = re.compile(r"^\s*(none|no|n/?a|not (stated|addressed|specified))\b", re.I)
_TOLERANCE = re.compile(r"(\d+(?:\.\d+)?)\s*(%|percent)", re.I)
_BOMA = re.compile(r"\bBOMA\b|ANSI", re.I)


def _short(s: Optional[str], n: int = 220) -> Optional[str]:
    if not s:
        return None
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def remeasurement_call(*, has_lease: bool, delta_sf: Optional[float], delta_pct: Optional[float],
                       remeasurement: Optional[str], deemed_final: Optional[str],
                       rsf_source: Optional[str]) -> dict:
    """Can the landlord correct this tenant's area? Returns {call, reason, clause}."""
    if delta_sf is None or delta_pct is None:
        return {"call": None, "reason": "No BOMA measurement for this suite", "clause": None}
    if abs(delta_pct) <= MATERIAL_PCT:
        return {"call": "MATCHES", "reason": f"Billed area is within {MATERIAL_PCT:g}% of BOMA", "clause": None}
    if delta_sf < 0:
        return {"call": "OVERBILLED",
                "reason": f"Tenant is billed on {abs(delta_sf):,.0f} SF more than BOMA measured — "
                          "it could claim a refund or a rent cut",
                "clause": _short(deemed_final or remeasurement)}
    if not has_lease:
        return {"call": "NO_LEASE", "reason": "No lease in the package — get it to see if the area can be corrected",
                "clause": None}

    remeasure = remeasurement if remeasurement and not _NO_RIGHT.match(remeasurement) else None
    tol = _TOLERANCE.search(remeasure or "")
    if tol and abs(delta_pct) <= float(tol.group(1)):
        return {"call": "NONE", "reason": f"Gap of {abs(delta_pct):.1f}% is inside the lease's "
                                          f"{tol.group(1)}% tolerance", "clause": _short(remeasure)}
    if remeasure and _REMEASURE.search(remeasure):
        return {"call": "STRONG", "reason": "Lease lets the landlord remeasure and adjust rent or share",
                "clause": _short(remeasure)}
    if deemed_final and _FIXED_AREA.search(deemed_final):
        return {"call": "NONE", "reason": "Lease fixes the area — it can't be changed until renewal",
                "clause": _short(deemed_final)}
    if rsf_source and _BOMA.search(rsf_source):
        return {"call": "NEGOTIABLE", "reason": "Lease measures by a BOMA standard the billed area doesn't meet, "
                                                "but has no adjustment clause", "clause": _short(rsf_source)}
    return {"call": "NEGOTIABLE", "reason": "Lease says nothing about remeasurement — correct it by agreement "
                                            "now or at renewal", "clause": None}


def _recovers_expenses(structure: Optional[str], has_actual_cam: bool) -> tuple[Optional[bool], Optional[str]]:
    if structure == "GROSS":
        return False, "Gross lease — expenses aren't passed through, so only base rent is affected"
    if structure == "MODIFIED_GROSS":
        return True, "Modified gross — tenant pays only some expenses; CAM gap is an upper bound"
    if structure == "NNN":
        return True, None
    if has_actual_cam:
        return True, None
    return None, "Expense terms unknown — assumed the tenant pays its share"


def audit(tenants: list[dict], *, boma_total_rsf: Optional[float], boma_total_usf: Optional[float],
          boma_load_factor: Optional[float], pool: Optional[float], pool_basis: Optional[str]) -> dict:
    """tenants: one dict per occupied suite, built by deal_metrics.compute_metrics."""
    cam_psf = pool / boma_total_rsf if pool and boma_total_rsf else None
    rows: list[dict] = []
    for t in tenants:
        billed, boma = t["billed_rsf"], t["boma_rsf"]
        delta = round(boma - billed, 2) if boma is not None and billed else None
        delta_pct = round(delta / billed * 100, 2) if delta is not None else None
        psf = t["rent_psf"] or None
        boma_share = round(boma / boma_total_rsf * 100, 3) if boma is not None and boma_total_rsf else None

        recovers, expense_note = _recovers_expenses(t["expense_structure"], t["billed_cam"] is not None)
        if t["base_year"]:
            expense_note = f"Base year {t['base_year']} — tenant pays only increases; CAM gap is an upper bound"
        if t["billed_cam"] is not None:
            billed_cam, billed_cam_basis = t["billed_cam"], t["billed_cam_basis"]
        elif cam_psf and billed and recovers is not False:
            billed_cam, billed_cam_basis = billed * cam_psf, "estimated (billed SF × pool rate)"
        else:
            billed_cam, billed_cam_basis = None, None
        correct_cam = (boma * cam_psf if boma is not None and cam_psf and recovers is not False
                       else 0.0 if recovers is False else None)
        cam_gap = (correct_cam - billed_cam if correct_cam is not None and billed_cam is not None
                   else 0.0 if recovers is False and delta is not None else None)
        rent_gap = delta * psf if delta is not None and psf else None
        total_gap = (rent_gap or 0) + (cam_gap or 0) if rent_gap is not None or cam_gap is not None else None

        rows.append({
            "tenantId": t["id"],
            "name": t["name"],
            "suite": t["suite"],
            "billedRsf": billed,
            "billedRsfSource": t["billed_rsf_source"],
            "bomaRsf": boma,
            "bomaUsf": t["boma_usf"],
            "deltaSF": delta,
            "deltaPct": delta_pct,
            "billedLoadFactor": round(billed / t["boma_usf"], 3) if billed and t["boma_usf"] else None,
            "bomaLoadFactor": round(boma / t["boma_usf"], 3) if boma and t["boma_usf"] else None,
            "billedShare": t["billed_share"],
            "billedShareSource": t["billed_share_source"],
            "bomaShare": boma_share,
            "rentPSF": round(psf, 2) if psf else None,
            "baseRentGap": _r(rent_gap),
            "billedCam": _r(billed_cam),
            "billedCamBasis": billed_cam_basis,
            "correctCam": _r(correct_cam),
            "camGap": _r(cam_gap),
            "totalGap": _r(total_gap),
            "correctedAnnualRent": _r(boma * psf) if boma is not None and psf else None,
            "recoversExpenses": recovers,
            "expenseNote": expense_note,
            "leverage": remeasurement_call(
                has_lease=t["has_lease"], delta_sf=delta, delta_pct=delta_pct,
                remeasurement=t["remeasurement"], deemed_final=t["deemed_final"], rsf_source=t["rsf_source"]),
            "terms": {k: t[k] for k in ("expense_structure_text", "cam_cap", "recoverable", "exclusions",
                                        "admin_fee", "gross_up", "base_year", "lease_share", "lease_share_basis")},
            "leaseFile": t["lease_file"],
        })

    measured = [r for r in rows if r["deltaSF"] is not None]
    under = [r for r in measured if r["deltaSF"] > 0 and r["deltaPct"] > MATERIAL_PCT]
    over = [r for r in measured if r["deltaSF"] < 0 and abs(r["deltaPct"]) > MATERIAL_PCT]
    with_usf = [r for r in measured if r["bomaUsf"]]
    usf = sum(r["bomaUsf"] for r in with_usf)
    calls: dict[str, int] = {}
    for r in measured:
        c = r["leverage"]["call"]
        if c:
            calls[c] = calls.get(c, 0) + 1

    def total(key: str, group: list[dict]) -> Optional[float]:
        vals = [r[key] for r in group if r[key] is not None]
        return _r(sum(vals)) if vals else None

    collectible = [r for r in under if r["leverage"]["call"] in ("STRONG", "NEGOTIABLE")]
    pending = [r for r in under if r["leverage"]["call"] == "NO_LEASE"]
    return {
        "available": bool(measured),
        "tenants": rows,
        "summary": {
            "suitesMeasured": len(measured),
            "suitesUnderbilled": len(under),
            "suitesOverbilled": len(over),
            "underbilledSF": round(sum(r["deltaSF"] for r in under), 2),
            "overbilledSF": round(sum(-r["deltaSF"] for r in over), 2),
            "baseRentUpside": total("baseRentGap", under),
            "camUpside": total("camGap", under),
            "totalUpside": total("totalGap", under),
            "collectibleUpside": total("totalGap", collectible),
            "pendingUpside": total("totalGap", pending),
            "overbilledExposure": _r(-sum(r["totalGap"] for r in over if r["totalGap"] is not None)) if over else None,
            "expensePool": _r(pool),
            "expensePoolBasis": pool_basis,
            "camRatePSF": round(cam_psf, 2) if cam_psf else None,
            "bomaLoadFactor": round(boma_load_factor, 3) if boma_load_factor else (
                round(boma_total_rsf / boma_total_usf, 3) if boma_total_rsf and boma_total_usf else None),
            "billedLoadFactor": round(sum(r["billedRsf"] for r in with_usf) / usf, 3) if usf else None,
            "leverage": calls,
        },
    }


def _r(x: Any) -> Optional[float]:
    return round(x, 2) if isinstance(x, (int, float)) else None
