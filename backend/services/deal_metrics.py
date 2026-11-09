"""
Deal metrics, verification, and scoring — computed in code, not by the model.

Claude extracts what each document says. Everything derived from those
extractions — tenant roster, RSF reconciliation, WALT, AR, arithmetic
checks, the 0-100 score — is calculated here, so every number on the
dashboard traces back to a document and a formula.

Entry points:
    compute_metrics(extractions, as_of)  -> metrics dict (also fed to synthesis)
    build_report(...)                    -> dashboard payload (frontend DealAnalysis)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from services import lease_audit

# ── Thresholds ───────────────────────────────────────────────────────────────

RSF_ALERT_PCT = 5.0          # BOMA vs rent roll gap that fires the RSF Recovery Alert
RSF_NOTICE_PCT = 2.0         # smaller gaps are noted, not alerted
CONCENTRATION_PCT = 25.0     # single-tenant share of rent that counts as concentration
NEAR_TERM_MONTHS = 12        # expirations inside this window are near-term rollover
CHECK_PASS_PCT = 1.0         # arithmetic checks within 1% pass
STALE_MONTHS = 3
CHECK_WARN_PCT = 5.0         # 1-5% is a warning, over 5% fails

RENT_ROLL_TYPES = ("RENT_ROLL", "RENT_ROLL_XLSX")
FINANCIAL_TYPES = ("MANAGEMENT_REPORT", "FINANCIAL_MODEL", "CAM_RECONCILIATION")

# The five document groups that make up a complete package (4 points each).
CORE_DOC_GROUPS = [
    ("rent_roll", "Rent roll", RENT_ROLL_TYPES),
    ("leases", "Executed leases", ("LEASE", "LEASE_ABSTRACT")),
    ("boma", "BOMA measurement", ("BOMA",)),
    ("financials", "Operating financials", FINANCIAL_TYPES),
    ("county", "County property appraiser record", ("COUNTY_PA",)),
]

DOC_REQUEST_REASONS = {
    "rent_roll": "Current tenant roster is the base for every rent and RSF figure.",
    "leases": "Executed leases confirm rent, term, and expiration for each tenant.",
    "boma": "Certified measurements are the only way to test billed square footage.",
    "financials": "A management report or T-12 is needed to verify NOI and collections.",
    "county": "The county record gives an independent building area to check against.",
}


# ── Value parsing ────────────────────────────────────────────────────────────

def val(x: Any) -> Any:
    """Unwrap {value, confidence, source_text} fields."""
    if isinstance(x, dict) and "value" in x:
        return x.get("value")
    return x


def num(x: Any) -> Optional[float]:
    x = val(x)
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return None
        negative = s.startswith("(") and s.endswith(")")
        s = re.sub(r"[^0-9.\-]", "", s)
        if s in ("", "-", ".", "-."):
            return None
        try:
            value = float(s)
        except ValueError:
            return None
        return -abs(value) if negative else value
    return None


def text(x: Any) -> Optional[str]:
    x = val(x)
    if x is None:
        return None
    s = str(x).strip()
    return s or None


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y",
                 "%d %B %Y", "%d %b %Y", "%Y/%m/%d", "%m-%d-%Y", "%B %Y", "%b %Y",
                 "%m/%Y", "%Y-%m")


def parse_date(x: Any) -> Optional[date]:
    x = val(x)
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip().replace("Sept ", "Sep ")
    if not s or s.lower() in ("n/a", "na", "mtm", "none", "null", "-"):
        return None
    s = re.sub(r"T.*$", "", s) if re.match(r"\d{4}-\d{2}-\d{2}T", s) else s
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def months_until(target: date, today: date) -> int:
    months = (target.year - today.year) * 12 + (target.month - today.month)
    if target.day < today.day:
        months -= 1
    return months


def money(x: float) -> str:
    return f"${x:,.0f}"


def round_or_none(x: Optional[float], digits: int = 2) -> Optional[float]:
    return None if x is None else round(x, digits)


# ── Name and suite matching ──────────────────────────────────────────────────

_NAME_STOPWORDS = {
    "inc", "llc", "corp", "corporation", "co", "company", "the", "na", "national",
    "association", "a", "an", "of", "ltd", "lp", "llp", "pllc", "pa", "dba", "and",
    "group", "services", "service",
}


def name_tokens(name: Optional[str]) -> set[str]:
    if not name:
        return set()
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    return {w for w in words if w not in _NAME_STOPWORDS}


def names_match(a: Optional[str], b: Optional[str]) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return False
    if ta <= tb or tb <= ta:
        return True
    return len(ta & tb) / len(ta | tb) >= 0.5


def suite_label(s: Optional[str]) -> str:
    if not s:
        return "suite not listed"
    return s if re.match(r"(?i)\s*(suite|ste|unit|space)\b", s) else f"Suite {s}"


def norm_suite(s: Any) -> Optional[str]:
    s = text(s)
    if not s:
        return None
    s = re.sub(r"(?i)\b(suite|ste|unit|space|#|no\.?)\b", " ", s)
    s = re.sub(r"[^A-Za-z0-9]", "", s).upper().lstrip("0")
    return s or None


# ── Source records ───────────────────────────────────────────────────────────

@dataclass
class LeaseRecord:
    tenant_name: Optional[str]
    suite: Optional[str]
    rsf: Optional[float]
    start: Optional[date]
    end: Optional[date]
    annual_rent: Optional[float]
    monthly_rent: Optional[float]
    rent_psf: Optional[float]
    escalation: Optional[str]
    expense_structure: Optional[str]
    cam_cap: Optional[str]
    renewal_options: Optional[str]
    ti_allowance: Optional[float]
    remeasurement_rights: Optional[str]
    premises_address: Optional[str]
    missing_fields: list[str]
    filename: str
    source: str  # "lease" or "abstract"
    confidence: Optional[float] = None
    pro_rata_share: Optional[float] = None
    pro_rata_basis: Optional[str] = None
    recoverable_expenses: Optional[str] = None
    expense_exclusions: Optional[str] = None
    admin_fee: Optional[str] = None
    gross_up: Optional[str] = None
    base_year: Optional[str] = None
    area_deemed_final: Optional[str] = None
    rsf_source_text: Optional[str] = None


@dataclass
class TenantRecord:
    name: str
    suite: Optional[str] = None
    rr_rsf: Optional[float] = None
    rr_start: Optional[date] = None
    rr_end: Optional[date] = None
    rr_annual: Optional[float] = None
    rr_monthly: Optional[float] = None
    rr_psf: Optional[float] = None
    rr_status: Optional[str] = None
    month_to_month: bool = False
    ar_balance: Optional[float] = None
    ar_over_60: Optional[float] = None
    ar_over_90: Optional[float] = None
    ar_note: Optional[str] = None
    rr_cam_monthly: Optional[float] = None
    rr_share: Optional[float] = None
    lease: Optional[LeaseRecord] = None
    boma_rsf: Optional[float] = None
    boma_usf: Optional[float] = None
    sources: list[str] = field(default_factory=list)


def _confidence(extraction: dict) -> Optional[float]:
    scores = [num(v.get("confidence")) for v in extraction.values()
              if isinstance(v, dict) and "confidence" in v]
    scores = [s for s in scores if s is not None]
    return round(sum(scores) / len(scores), 2) if scores else None


def _lease_from_extraction(e: dict, filename: str, missing: list[str]) -> LeaseRecord:
    escalation = text(e.get("escalation_schedule")) or text(e.get("escalation_type"))
    pct = num(e.get("escalation_percentage"))
    if pct is not None and escalation and str(pct).rstrip("0").rstrip(".") not in escalation:
        escalation = f"{escalation} ({pct:g}%)"
    elif pct is not None and not escalation:
        escalation = f"{pct:g}% annual"
    return LeaseRecord(
        tenant_name=text(e.get("tenant_name")),
        suite=text(e.get("suite_number")),
        rsf=num(e.get("rentable_sf")),
        start=parse_date(e.get("lease_commencement_date")),
        end=parse_date(e.get("lease_expiration_date")),
        annual_rent=num(e.get("base_rent_annual")),
        monthly_rent=num(e.get("base_rent_monthly")),
        rent_psf=num(e.get("rent_per_sf")),
        escalation=escalation,
        expense_structure=text(e.get("expense_structure")),
        cam_cap=text(e.get("cam_cap")),
        renewal_options=text(e.get("renewal_options")),
        ti_allowance=num(e.get("ti_allowance")),
        remeasurement_rights=text(e.get("remeasurement_rights")),
        premises_address=text(e.get("premises_address")),
        missing_fields=list(missing or []),
        filename=filename,
        source="lease",
        confidence=_confidence(e),
        pro_rata_share=num(e.get("pro_rata_share_pct")),
        pro_rata_basis=text(e.get("pro_rata_share_basis")),
        recoverable_expenses=text(e.get("recoverable_expenses")),
        expense_exclusions=text(e.get("expense_exclusions")),
        admin_fee=text(e.get("admin_fee")),
        gross_up=text(e.get("gross_up")),
        base_year=text(e.get("base_year")),
        area_deemed_final=text(e.get("area_deemed_final")),
        rsf_source_text=_source_text(e.get("rentable_sf")),
    )


def _source_text(field_value: Any) -> Optional[str]:
    return text(field_value.get("source_text")) if isinstance(field_value, dict) else None


def _lease_from_abstract_row(r: dict, filename: str) -> LeaseRecord:
    missing = [f for f, v in (("tenant_name", r.get("tenant_name")), ("rentable_sf", r.get("rsf")),
                              ("lease_expiration_date", r.get("lease_end")),
                              ("base_rent_annual", r.get("annual_base_rent"))) if val(v) in (None, "")]
    return LeaseRecord(
        tenant_name=text(r.get("tenant_name")), suite=text(r.get("suite")), rsf=num(r.get("rsf")),
        start=parse_date(r.get("lease_start")), end=parse_date(r.get("lease_end")),
        annual_rent=num(r.get("annual_base_rent")), monthly_rent=None, rent_psf=num(r.get("rent_psf")),
        escalation=text(r.get("escalations")), expense_structure=text(r.get("expense_structure")),
        cam_cap=None, renewal_options=text(r.get("renewal_options")), ti_allowance=None,
        remeasurement_rights=None, premises_address=None, missing_fields=missing,
        filename=filename, source="abstract",
    )


@dataclass
class Sources:
    present_types: set[str]
    rent_roll_rows: list[dict]
    rent_roll_summary: dict
    rent_roll_file: Optional[str]
    rent_roll_date: Optional[date]
    leases: list[LeaseRecord]
    boma_suites: list[dict]
    boma_totals: dict
    boma_file: Optional[str]
    ar_entries: list[dict]
    mgmt: dict
    mgmt_file: Optional[str]
    model: dict
    county: dict
    cam_rec: dict
    failed_extractions: list[dict]


def collect_sources(extractions: list[dict]) -> Sources:
    present: set[str] = set()
    rr_rows: list[dict] = []
    rr_summary: dict = {}
    rr_file = None
    rr_date: Optional[date] = None
    mgmt_rows: list[dict] = []
    mgmt_summary: dict = {}
    leases: list[LeaseRecord] = []
    boma_suites: list[dict] = []
    boma_totals: dict = {}
    boma_file = None
    ar_entries: list[dict] = []
    mgmt: dict = {}
    mgmt_file = None
    model: dict = {}
    county: dict = {}
    cam_rec: dict = {}
    failed: list[dict] = []

    for ext in extractions:
        doc_type = ext.get("doc_type")
        data = ext.get("extraction") or {}
        filename = ext.get("filename", "")
        if ext.get("parse_error") or not data:
            failed.append({"filename": filename, "doc_type": doc_type,
                           "error": ext.get("parse_error") or "Nothing extracted"})
            continue
        present.add(doc_type)

        if doc_type in RENT_ROLL_TYPES:
            rows = data.get("tenants") or []
            if len(rows) > len(rr_rows):  # use the fullest rent roll if several were uploaded
                rr_rows, rr_summary, rr_file = rows, data.get("summary") or {}, filename
                rr_date = parse_date(data.get("as_of_date"))
        elif doc_type == "LEASE":
            leases.append(_lease_from_extraction(data, filename, ext.get("missing_fields", [])))
        elif doc_type == "LEASE_ABSTRACT":
            leases.extend(_lease_from_abstract_row(r, filename) for r in data.get("leases") or [])
        elif doc_type == "BOMA":
            boma_suites.extend(data.get("suites") or [])
            if not boma_totals and data.get("building_totals"):
                boma_totals, boma_file = data["building_totals"], filename
            boma_file = boma_file or filename
        elif doc_type == "MANAGEMENT_REPORT":
            mgmt, mgmt_file = data, filename
            ar_entries.extend(data.get("ar_aging") or [])
            if data.get("rent_roll"):
                mgmt_rows, mgmt_summary = data["rent_roll"], data.get("rent_roll_summary") or {}
        elif doc_type == "FINANCIAL_MODEL":
            model = data
        elif doc_type == "COUNTY_PA":
            county = data
        elif doc_type == "CAM_RECONCILIATION":
            cam_rec = data

    # A management report's rent roll stands in when no separate rent roll was uploaded.
    if not rr_rows and mgmt_rows:
        rr_rows, rr_summary, rr_file = mgmt_rows, mgmt_summary, mgmt_file
        rr_date = parse_date(mgmt.get("report_date"))
        present.add("RENT_ROLL")

    return Sources(present, rr_rows, rr_summary, rr_file, rr_date, leases, boma_suites, boma_totals,
                   boma_file, ar_entries, mgmt, mgmt_file, model, county, cam_rec, failed)


def _merge_duplicate_leases(leases: list[LeaseRecord]) -> list[LeaseRecord]:
    """An amendment and its original lease describe one tenancy; keep the latest expiration."""
    merged: list[LeaseRecord] = []
    for lease in leases:
        twin = next((m for m in merged if names_match(m.tenant_name, lease.tenant_name)
                     and (not m.suite or not lease.suite or norm_suite(m.suite) == norm_suite(lease.suite))), None)
        if twin is None:
            merged.append(lease)
            continue
        newer = lease if (lease.end or date.min) > (twin.end or date.min) else twin
        older = twin if newer is lease else lease
        for attr in ("tenant_name", "suite", "rsf", "start", "annual_rent", "monthly_rent", "rent_psf",
                     "escalation", "expense_structure", "cam_cap", "renewal_options", "ti_allowance",
                     "remeasurement_rights", "premises_address", "pro_rata_share", "pro_rata_basis", "recoverable_expenses", "expense_exclusions", "admin_fee", "gross_up", "base_year", "area_deemed_final", "rsf_source_text"):
            if getattr(newer, attr) in (None, ""):
                setattr(newer, attr, getattr(older, attr))
        newer.filename = f"{newer.filename}, {older.filename}"
        newer.missing_fields = [f for f in newer.missing_fields if f in older.missing_fields]
        merged[merged.index(twin)] = newer
    return merged


def _find_tenant(tenants: list[TenantRecord], name: Optional[str], suite: Optional[str]) -> Optional[TenantRecord]:
    key = norm_suite(suite)
    if key:
        by_suite = [t for t in tenants if norm_suite(t.suite) == key]
        if len(by_suite) == 1:
            return by_suite[0]
        named = [t for t in by_suite if names_match(t.name, name)]
        if named:
            return named[0]
    matches = [t for t in tenants if names_match(t.name, name)]
    return matches[0] if len(matches) == 1 else None


_LANDLORD_USE = re.compile(
    r"\b(maintenance|storage room|janitor|mechanical|electrical|boiler|elevator|management office|"
    r"mgmt\.? office|leasing office|common area|restrooms?)\b", re.I)
_MONTH_TO_MONTH = re.compile(r"\b(mtm|m-t-m|month[\s-]*to[\s-]*month|mo\.?\s*to\s*mo\.?)\b", re.I)


def _is_landlord_use(row: dict) -> bool:
    """Space the landlord keeps for itself (maintenance, storage, management office): not leased, not vacant."""
    if val(row.get("is_landlord_use")) is True:
        return True
    name = text(row.get("tenant_name")) or ""
    rent = num(row.get("monthly_base_rent")) or num(row.get("annual_base_rent"))
    return bool(_LANDLORD_USE.search(name)) and not rent and not name.lower().startswith("vacant")


def _is_month_to_month(row: dict) -> bool:
    return any(_MONTH_TO_MONTH.search(str(val(row.get(k)) or "")) for k in ("status", "lease_end"))


def tenant_key(name: str) -> str:
    return " ".join(sorted(name_tokens(name))) or name.lower()


def _is_vacant(row: dict) -> bool:
    if val(row.get("is_vacant")) is True:
        return True
    name = (text(row.get("tenant_name")) or "").lower()
    return not name or name.startswith("vacant") or name in ("available", "n/a")


# ── Metrics ──────────────────────────────────────────────────────────────────

def compute_metrics(extractions: list[dict], as_of: Optional[date] = None) -> dict:
    """Build the tenant roster and every derived figure from the extractions."""
    today = as_of or date.today()
    src = collect_sources(extractions)
    leases = _merge_duplicate_leases(src.leases)

    tenants: list[TenantRecord] = []
    vacant_rsf = 0.0
    vacant_suites: list[str] = []
    landlord_use: list[dict] = []
    for row in src.rent_roll_rows:
        rsf = num(row.get("rsf"))
        if _is_landlord_use(row):
            landlord_use.append({"suite": text(row.get("suite")), "name": text(row.get("tenant_name")), "rsf": rsf})
            continue
        if _is_vacant(row):
            vacant_rsf += rsf or 0
            if text(row.get("suite")):
                vacant_suites.append(text(row.get("suite")))
            continue
        tenants.append(TenantRecord(
            name=text(row.get("tenant_name")) or "Unnamed tenant",
            suite=text(row.get("suite")), rr_rsf=rsf,
            rr_start=parse_date(row.get("lease_start")), rr_end=parse_date(row.get("lease_end")),
            rr_annual=num(row.get("annual_base_rent")), rr_monthly=num(row.get("monthly_base_rent")),
            rr_psf=num(row.get("rent_psf")), rr_status=text(row.get("status")),
            month_to_month=_is_month_to_month(row),
            ar_balance=num(row.get("ar_balance")), ar_over_60=num(row.get("ar_over_60")),
            ar_over_90=num(row.get("ar_over_90")), sources=["rent_roll"],
            rr_cam_monthly=num(row.get("monthly_cam_charges")), rr_share=num(row.get("pro_rata_share_pct")),
        ))
    has_rent_roll = bool(tenants) or vacant_rsf > 0

    orphan_leases: list[LeaseRecord] = []
    for lease in leases:
        match = _find_tenant(tenants, lease.tenant_name, lease.suite)
        if match:
            match.lease = lease
            match.sources.append(lease.source)
        elif has_rent_roll:
            orphan_leases.append(lease)
        else:
            tenants.append(TenantRecord(name=lease.tenant_name or "Unnamed tenant", suite=lease.suite,
                                        lease=lease, sources=[lease.source]))

    unmatched_boma: list[dict] = []
    for suite in src.boma_suites:
        rsf = num(suite.get("rentable_sf"))
        match = _find_tenant(tenants, text(suite.get("tenant_name")), text(suite.get("suite")))
        if match and match.boma_rsf is None:
            match.boma_rsf = rsf
            match.boma_usf = num(suite.get("usable_sf"))
            match.sources.append("boma")
        else:
            unmatched_boma.append(suite)
    if not has_rent_roll:
        for suite in unmatched_boma:
            if _is_vacant(suite) or not text(suite.get("tenant_name")):
                vacant_rsf += num(suite.get("rentable_sf")) or 0
                if text(suite.get("suite")):
                    vacant_suites.append(text(suite.get("suite")))

    for entry in src.ar_entries:
        match = _find_tenant(tenants, text(entry.get("tenant_name")), None)
        if not match:
            continue
        match.ar_balance = num(entry.get("total_outstanding"))
        match.ar_over_60 = num(entry.get("over_60_days"))
        match.ar_over_90 = num(entry.get("over_90_days"))
        match.ar_note = text(entry.get("note"))
        if "ar_aging" not in match.sources:
            match.sources.append("ar_aging")

    # Per-tenant figures
    rows: list[dict] = []
    conflicts: list[dict] = []
    for i, t in enumerate(tenants):
        lease = t.lease
        rsf = t.rr_rsf or (lease.rsf if lease else None) or t.boma_rsf
        annual = (t.rr_annual or (t.rr_monthly * 12 if t.rr_monthly else None)
                  or (lease.annual_rent if lease else None)
                  or (lease.monthly_rent * 12 if lease and lease.monthly_rent else None))
        expiry = (lease.end if lease and lease.end else None) or t.rr_end
        start = (lease.start if lease and lease.start else None) or t.rr_start
        if lease and lease.end and t.rr_end and abs((lease.end - t.rr_end).days) > 31:
            conflicts.append({"tenant": t.name, "lease_end": lease.end.isoformat(),
                              "rent_roll_end": t.rr_end.isoformat(), "lease_file": lease.filename})
        mtm = t.month_to_month and not (lease and lease.end)
        months = months_until(expiry, today) if expiry else None
        if months is None or months <= NEAR_TERM_MONTHS:
            risk = "HIGH"
        elif months <= 24:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        over_60 = max(t.ar_over_60 or 0, t.ar_over_90 or 0)
        balance = t.ar_balance or 0
        if over_60 > 0:
            ar_status = "DELINQUENT"
        elif balance > 0:
            ar_status = "AT_RISK"
        else:
            ar_status = "CURRENT"

        rows.append({
            "id": f"t-{i + 1}",
            "name": t.name,
            "suite": t.suite or "",
            "rsf": round(rsf or 0, 2),
            "rentRollRsf": t.rr_rsf,
            "leaseRsf": lease.rsf if lease else None,
            "bomaRsf": t.boma_rsf,
            "rsfDelta": round(t.boma_rsf - rsf, 2) if t.boma_rsf is not None and rsf else None,
            "monthlyRent": round((annual or 0) / 12, 2),
            "annualRent": round(annual or 0, 2),
            "rentPSF": round(annual / rsf, 2) if annual and rsf else 0,
            "leaseStart": start.isoformat() if start else None,
            "leaseExpiry": expiry.isoformat() if expiry else None,
            "monthsRemaining": months,
            "monthToMonth": mtm,
            "incomeConcentration": 0.0,  # filled once the total is known
            "riskLevel": risk,
            "arStatus": ar_status,
            "arBalance": round(max(balance, 0), 2),
            "arOver60": round(over_60, 2),
            "arNote": t.ar_note,
            "hasLease": lease is not None,
            "sources": t.sources,
        })

    total_rent = sum(r["annualRent"] for r in rows)
    for r in rows:
        r["incomeConcentration"] = round(r["annualRent"] / total_rent * 100, 1) if total_rent else 0.0

    occupied_rsf = sum(r["rentRollRsf"] or 0 for r in rows) if has_rent_roll else sum(r["rsf"] for r in rows)
    occupied_source = "rent roll" if has_rent_roll else ("leases" if leases else None)
    leasable_rsf = occupied_rsf + vacant_rsf

    boma_total = num(src.boma_totals.get("total_rentable_sf"))
    if boma_total is None and src.boma_suites:
        boma_total = sum(num(s.get("rentable_sf")) or 0 for s in src.boma_suites) or None
    building_rsf = boma_total or num(src.rent_roll_summary.get("total_rsf")) or (leasable_rsf or None)

    # Without a rent roll, leases alone can't say what's vacant.
    vacancy_pct = round(vacant_rsf / building_rsf * 100, 1) if building_rsf and has_rent_roll else None
    avg_psf = total_rent / occupied_rsf if total_rent and occupied_rsf else None

    # RSF reconciliation: certified BOMA area vs the area being billed.
    # A rent roll covers the whole building, so it's compared to the BOMA building total.
    # Leases alone cover only their own suites, so only those suites are compared.
    if has_rent_roll:
        boma_compare, billed_compare = boma_total, leasable_rsf
    else:
        matched = [r for r in rows if r["bomaRsf"] is not None and r["rsf"]]
        boma_compare = sum(r["bomaRsf"] for r in matched) or None
        billed_compare = sum(r["rsf"] for r in matched)
        if matched:
            occupied_source = f"leases ({len(matched)} suite{'s' if len(matched) != 1 else ''})"
    rsf_rec: dict[str, Any] = {
        "bomaTotalSF": round(boma_compare, 2) if boma_compare else 0,
        "rentRollOccupiedSF": round(billed_compare or 0, 2),
        "occupiedSource": occupied_source,
        "deltaSF": 0, "deltaPercent": 0, "estimatedAnnualRecovery": 0,
        "alertTriggered": False, "comparable": False,
        "countyTotalSF": num(src.county.get("total_sf")),
        "countyNote": None,
    }
    if boma_compare and billed_compare:
        delta = boma_compare - billed_compare
        pct = delta / billed_compare * 100
        rsf_rec.update({
            "deltaSF": round(delta, 2),
            "deltaPercent": round(pct, 2),
            "estimatedAnnualRecovery": round(delta * avg_psf, 2) if delta > 0 and avg_psf else 0,
            "alertTriggered": abs(pct) > RSF_ALERT_PCT,
            "comparable": True,
        })
    # Lease audit: suite-by-suite area and CAM, and whether the leases let the landlord fix it.
    pool, pool_basis = _expense_pool(src)
    cam_rows = {tenant_key(text(r.get("tenant_name")) or ""): r
                for r in (src.cam_rec.get("tenant_reconciliations") or []) if text(r.get("tenant_name"))}
    audit_inputs = []
    for t, row in zip(tenants, rows):
        lease = t.lease
        cam_row = cam_rows.get(tenant_key(t.name)) or next(
            (r for k, r in cam_rows.items() if names_match(text(r.get("tenant_name")), t.name)), None)
        billed_cam, billed_cam_basis = None, None
        if t.rr_cam_monthly is not None:
            billed_cam, billed_cam_basis = t.rr_cam_monthly * 12, "rent roll (monthly × 12)"
        elif cam_row and num(cam_row.get("amount_billed")) is not None:
            billed_cam, billed_cam_basis = num(cam_row.get("amount_billed")), "CAM reconciliation"
        share, share_src = t.rr_share, "rent roll" if t.rr_share is not None else None
        if share is None and cam_row and num(cam_row.get("pro_rata_share_pct")) is not None:
            share, share_src = num(cam_row.get("pro_rata_share_pct")), "CAM reconciliation"
        if share is None and lease and lease.pro_rata_share is not None:
            share, share_src = lease.pro_rata_share, "lease"
        billed_rsf = t.rr_rsf or (lease.rsf if lease else None)
        audit_inputs.append({
            "id": row["id"], "name": t.name, "suite": row["suite"],
            "billed_rsf": billed_rsf, "billed_rsf_source": "rent roll" if t.rr_rsf else ("lease" if billed_rsf else None),
            "boma_rsf": t.boma_rsf, "boma_usf": t.boma_usf,
            "rent_psf": row["annualRent"] / billed_rsf if row["annualRent"] and billed_rsf else None,
            "billed_cam": billed_cam, "billed_cam_basis": billed_cam_basis,
            "billed_share": share, "billed_share_source": share_src,
            "has_lease": lease is not None and lease.source == "lease",
            "expense_structure": _expense_label(lease.expense_structure) if lease else None,
            "expense_structure_text": lease.expense_structure if lease else None,
            "remeasurement": lease.remeasurement_rights if lease else None,
            "deemed_final": lease.area_deemed_final if lease else None,
            "rsf_source": lease.rsf_source_text if lease else None,
            "base_year": lease.base_year if lease else None,
            "cam_cap": lease.cam_cap if lease else None,
            "recoverable": lease.recoverable_expenses if lease else None,
            "exclusions": lease.expense_exclusions if lease else None,
            "admin_fee": lease.admin_fee if lease else None,
            "gross_up": lease.gross_up if lease else None,
            "lease_share": lease.pro_rata_share if lease else None,
            "lease_share_basis": lease.pro_rata_basis if lease else None,
            "lease_file": lease.filename if lease else None,
        })
    audit = lease_audit.audit(
        audit_inputs, boma_total_rsf=boma_total, boma_total_usf=num(src.boma_totals.get("total_usable_sf")),
        boma_load_factor=num(src.boma_totals.get("building_load_factor")), pool=pool, pool_basis=pool_basis)

    # The building-wide gap is worth base rent plus the CAM those feet should carry.
    cam_psf = audit["summary"]["camRatePSF"]
    if rsf_rec["comparable"] and rsf_rec["deltaSF"] > 0:
        base = rsf_rec["deltaSF"] * avg_psf if avg_psf else 0
        cam = rsf_rec["deltaSF"] * cam_psf if cam_psf else 0
        rsf_rec.update({"baseRentRecovery": round(base, 2), "camRecovery": round(cam, 2),
                        "estimatedAnnualRecovery": round(base + cam, 2), "camRatePSF": cam_psf,
                        "averageRentPSF": round(avg_psf, 2) if avg_psf else None})
    else:
        rsf_rec.update({"baseRentRecovery": 0, "camRecovery": 0, "camRatePSF": cam_psf,
                        "averageRentPSF": round(avg_psf, 2) if avg_psf else None})

    county_total = rsf_rec["countyTotalSF"]
    if county_total:
        canopy = (num(src.county.get("canopy_sf")) or 0) + (num(src.county.get("porch_sf")) or 0)
        if canopy:
            rsf_rec["countyNote"] = (f"County total includes {canopy:,.0f} SF of canopy/porch, "
                                     f"which is not rentable area.")

    known = [r for r in rows if r["monthsRemaining"] is not None]
    known_rent = sum(r["annualRent"] for r in known)
    walt = (sum(r["annualRent"] * max(r["monthsRemaining"], 0) for r in known) / known_rent
            if known_rent else None)

    noi, noi_basis = _noi(src)
    cap_rate = num(src.model.get("cap_rate_going_in"))
    cap_basis = "Going-in cap rate (financial model)" if cap_rate is not None else None
    price = num(src.model.get("acquisition_price"))
    if cap_rate is None and price and noi:
        cap_rate, cap_basis = noi / price * 100, "NOI ÷ acquisition price"

    checks = _arithmetic_checks(src, leases, rows, occupied_rsf, vacant_rsf, total_rent, src.mgmt)

    doc_dates = [d for d in (src.rent_roll_date, parse_date(src.mgmt.get("report_date"))) if d]
    data_as_of = max(doc_dates) if doc_dates else None
    collection = src.mgmt.get("collection_summary") or {}
    contract_monthly = sum(r["monthlyRent"] for r in rows) if has_rent_roll else None
    billed_monthly = num(collection.get("billed_minimum_rent"))
    if billed_monthly is not None and contract_monthly:
        billing = _check("Contract rent vs billed rent", contract_monthly, billed_monthly,
                         "minimum rent billed this period vs sum of monthly contract rent",
                         src.mgmt_file or "management report", "$")
        if billing:
            billing["kind"] = "billing"
            if billing["status"] != "pass":
                gap = contract_monthly - billed_monthly
                billing["detail"] = (f"Leases call for {money(contract_monthly)}/mo; {money(billed_monthly)} was billed "
                                     f"({'short' if gap > 0 else 'over'} {money(abs(gap))}, {billing['deltaPct']:.1f}%)")
            checks.append(billing)

    property_address = (text(src.mgmt.get("property_address")) or text(src.county.get("property_address"))
                        or next((l.premises_address for l in leases if l.premises_address), None))

    return {
        "as_of": today.isoformat(),
        "present_types": sorted(src.present_types),
        "tenants": rows,
        "vacant_rsf": round(vacant_rsf, 2),
        "vacant_suites": vacant_suites,
        "building_rsf": round(building_rsf, 2) if building_rsf else None,
        "occupied_rsf": round(occupied_rsf, 2),
        "has_rent_roll": has_rent_roll,
        "rsf_reconciliation": rsf_rec,
        "lease_audit": audit,
        "unmatched_boma_suites": [{"suite": text(s.get("suite")), "tenant": text(s.get("tenant_name")),
                                   "rentable_sf": num(s.get("rentable_sf"))} for s in unmatched_boma],
        "financial": {
            "totalAnnualRent": round(total_rent, 2),
            "averageRentPSF": round(avg_psf, 2) if avg_psf else 0,
            "noi": round(noi, 2) if noi is not None else None,
            "noiBasis": noi_basis,
            "capRate": round(cap_rate, 2) if cap_rate is not None else None,
            "capRateBasis": cap_basis,
            "vacancy": vacancy_pct,
            "arDelinquency": round(sum(r["arOver60"] for r in rows), 2),
            "camRecoveryRatio": num(src.mgmt.get("cam_recovery_ratio_pct")),
        },
        "has_ar_aging": any(num(e.get(k)) is not None for e in src.ar_entries for k in ("over_60_days", "over_90_days"))
            or any(num(r.get(k)) is not None for r in src.rent_roll_rows for k in ("ar_over_60", "ar_over_90")),
        "data_as_of": data_as_of.isoformat() if data_as_of else None,
        "data_age_months": months_until(today, data_as_of) if data_as_of else None,
        "landlord_use": landlord_use,
        "has_ar_data": bool(src.ar_entries) or any(
            num(r.get(k)) is not None for r in src.rent_roll_rows for k in ("ar_balance", "ar_over_60", "ar_over_90")),
        "walt_months": round(walt, 1) if walt is not None else None,
        "walt_coverage_pct": round(known_rent / total_rent * 100, 1) if total_rent else 0,
        "leases": leases,
        "orphan_leases": [{"tenant": l.tenant_name, "suite": l.suite, "file": l.filename} for l in orphan_leases],
        "expiry_conflicts": conflicts,
        "arithmetic_checks": checks,
        "failed_extractions": src.failed_extractions,
        "property_address": property_address,
        "property_name": (text(src.mgmt.get("property_name")) or text(src.boma_totals.get("building_name"))
                          or text(src.model.get("property_name"))),
        "_sources": src,
    }


def _expense_pool(src: Sources) -> tuple[Optional[float], Optional[str]]:
    """Annual expenses tenants share. A CAM reconciliation is the real figure; opex is a stand-in."""
    total = num(src.cam_rec.get("total_cam_expenses"))
    if total:
        year = text(src.cam_rec.get("reconciliation_year"))
        return total, f"CAM reconciliation{' ' + year if year else ''}"
    for key, label in (("income_year_to_date", "year-to-date"), ("income_period_to_date", "period")):
        period = src.mgmt.get(key) or {}
        opex, months = num(period.get("operating_expenses")), num(period.get("months_covered"))
        if opex and months:
            span = text(period.get("period_label")) or f"{months:g} months"
            return opex * 12 / months, (f"Operating expenses annualized from {label} ({span}, management report) — "
                                        "all categories, before lease exclusions")
    return None, None


def _noi(src: Sources) -> tuple[Optional[float], Optional[str]]:
    year1 = num(src.model.get("noi_year_1"))
    if year1 is not None:
        return year1, "Year 1 NOI from the financial model"
    for key, label in (("income_year_to_date", "year-to-date"), ("income_period_to_date", "period")):
        period = src.mgmt.get(key) or {}
        noi = num(period.get("noi"))
        months = num(period.get("months_covered"))
        if noi is not None and months:
            span = text(period.get("period_label")) or f"{months:g} months"
            return noi * 12 / months, f"Annualized from {label} NOI ({span}, management report)"
    return None, None


def _check(label: str, stated: Optional[float], computed: Optional[float], formula: str,
           source: str, unit: str = "") -> Optional[dict]:
    if stated is None or computed is None:
        return None
    if stated == 0:
        delta_pct = 0.0 if abs(computed) < 0.01 else 100.0
    else:
        delta_pct = abs(computed - stated) / abs(stated) * 100
    status = "pass" if delta_pct <= CHECK_PASS_PCT else ("warning" if delta_pct <= CHECK_WARN_PCT else "fail")
    fmt = (lambda v: f"${v:,.2f}") if unit == "$" else (lambda v: f"{v:,.2f}{unit}")
    detail = None if status == "pass" else f"Stated {fmt(stated)}, computed {fmt(computed)} ({delta_pct:.1f}% off)"
    return {"label": label, "status": status, "stated": round(stated, 2), "computed": round(computed, 2),
            "deltaPct": round(delta_pct, 2), "formula": formula, "detail": detail, "source": source}


def _arithmetic_checks(src: Sources, leases: list[LeaseRecord], rows: list[dict], occupied: float,
                       vacant: float, total_rent: float, mgmt: dict) -> list[dict]:
    checks: list[Optional[dict]] = []
    s = src.rent_roll_summary
    rr = src.rent_roll_file or "rent roll"
    if rows and s:
        stated_total = num(s.get("total_rsf"))
        if stated_total is not None:
            checks.append(_check("Rent roll total RSF", stated_total, occupied + vacant,
                                 "sum(tenant RSF) + vacant RSF", rr, " SF"))
        checks.append(_check("Rent roll occupied RSF", num(s.get("occupied_rsf")), occupied,
                             "sum(occupied tenant RSF)", rr, " SF"))
        stated_annual = num(s.get("total_annual_rent"))
        if stated_annual is None and num(s.get("total_monthly_rent")) is not None:
            stated_annual = num(s.get("total_monthly_rent")) * 12
        rr_rent = sum((num(r.get("annual_base_rent")) or (num(r.get("monthly_base_rent")) or 0) * 12)
                      for r in src.rent_roll_rows if not _is_vacant(r))
        checks.append(_check("Rent roll total annual rent", stated_annual, rr_rent,
                             "sum(tenant annual base rent)", rr, "$"))
        if num(s.get("occupancy_rate")) is not None and (occupied + vacant):
            checks.append(_check("Rent roll occupancy", num(s.get("occupancy_rate")),
                                 occupied / (occupied + vacant) * 100, "occupied RSF ÷ total RSF", rr, "%"))

    for r in src.rent_roll_rows:
        if _is_vacant(r):
            continue
        name = text(r.get("tenant_name")) or "tenant"
        monthly, annual, rsf = num(r.get("monthly_base_rent")), num(r.get("annual_base_rent")), num(r.get("rsf"))
        if monthly and annual:
            checks.append(_check(f"Annual rent — {name}", annual, monthly * 12, "monthly rent × 12", rr, "$"))
        if annual and rsf:
            checks.append(_check(f"Rent PSF — {name}", num(r.get("rent_psf")), annual / rsf,
                                 "annual rent ÷ RSF", rr, "$"))

    for lease in leases:
        name = lease.tenant_name or "tenant"
        if lease.monthly_rent and lease.annual_rent:
            checks.append(_check(f"Lease annual rent — {name}", lease.annual_rent, lease.monthly_rent * 12,
                                 "monthly rent × 12", lease.filename, "$"))
        if lease.annual_rent and lease.rsf:
            checks.append(_check(f"Lease rent PSF — {name}", lease.rent_psf, lease.annual_rent / lease.rsf,
                                 "annual rent ÷ RSF", lease.filename, "$"))

    totals = src.boma_totals
    suite_sum = sum(num(x.get("rentable_sf")) or 0 for x in src.boma_suites)
    if suite_sum and num(totals.get("total_rentable_sf")):
        common = num(totals.get("common_area_sf"))
        check = _check("BOMA suites vs building total", num(totals.get("total_rentable_sf")), suite_sum,
                       "sum(suite rentable SF)", src.boma_file or "BOMA", " SF")
        if check and check["status"] != "pass":
            check["detail"] = (check["detail"] or "") + (
                ". Remaining area may be unlisted suites or building common area." if common else "")
        checks.append(check)

    for key, label in (("income_period_to_date", "period"), ("income_year_to_date", "year-to-date")):
        p = mgmt.get(key) or {}
        rev, opex = num(p.get("total_revenue")), num(p.get("operating_expenses"))
        if rev is not None and opex is not None:
            checks.append(_check(f"NOI ({label})", num(p.get("noi")), rev - opex,
                                 "total revenue − operating expenses", src.mgmt_file or "management report", "$"))

    bank = mgmt.get("bank_reconciliation") or {}
    if num(bank.get("bank_balance")) is not None and num(bank.get("gl_balance")) is not None:
        diff = num(bank.get("bank_balance")) - num(bank.get("gl_balance"))
        status = "pass" if abs(diff) < 0.01 else "fail"
        checks.append({"label": "Bank reconciliation", "status": status, "stated": num(bank.get("difference")),
                       "computed": round(diff, 2), "deltaPct": None, "formula": "bank balance − GL balance",
                       "detail": None if status == "pass" else f"Bank and GL differ by ${diff:,.2f}",
                       "source": src.mgmt_file or "management report"})
    return [c for c in checks if c]


# ── Score ────────────────────────────────────────────────────────────────────

def _cat(points: float, max_points: int, reasons: list[dict]) -> dict:
    return {"points": round(max(0.0, min(points, max_points)), 1), "max": max_points, "reasons": reasons}


def score_deal(m: dict, documents_uploaded: int, documents_extracted: int) -> dict:
    """Six-category score out of 100. Every point carries a reason."""
    present = set(m["present_types"])
    rows = m["tenants"]
    fin = m["financial"]
    rsf = m["rsf_reconciliation"]
    total_rent = fin["totalAnnualRent"]

    # 1. Data completeness (20): 4 per core document group
    reasons, pts = [], 0
    for key, label, types in CORE_DOC_GROUPS:
        has = bool(present & set(types)) or (key == "rent_roll" and m["has_rent_roll"])
        reasons.append({"text": label, "earned": has, "points": 4 if has else 0})
        pts += 4 if has else 0
    data = _cat(pts, 20, reasons)

    # 2. RSF alignment (20)
    if rsf["comparable"]:
        gap = abs(rsf["deltaPercent"])
        pts = 20 if gap <= RSF_NOTICE_PCT else 14 if gap <= RSF_ALERT_PCT else 8 if gap <= 10 else 2
        reasons = [{"text": f"BOMA and {rsf['occupiedSource']} differ by {gap:.1f}%",
                    "earned": gap <= RSF_NOTICE_PCT, "points": pts}]
        if not m["has_rent_roll"]:
            reasons.append({"text": "No rent roll — only leased suites could be compared",
                            "earned": False, "points": min(0, 10 - pts)})
            pts = min(pts, 10)
    else:
        pts = 5 if (m["occupied_rsf"] or rsf["bomaTotalSF"]) else 0
        reasons = [{"text": "Only one RSF source — variance can't be tested", "earned": False, "points": pts}]
    per_tenant = [r for r in rows if r["rsfDelta"] is not None and r["rsf"]
                  and abs(r["rsfDelta"]) / r["rsf"] * 100 > RSF_ALERT_PCT]
    if per_tenant:
        pts -= min(4, len(per_tenant))
        reasons.append({"text": f"{len(per_tenant)} suite(s) off BOMA by more than {RSF_ALERT_PCT:g}%",
                        "earned": False, "points": -min(4, len(per_tenant))})
    rsf_cat = _cat(pts, 20, reasons)

    # 3. Financial integrity (20)
    reasons, pts = [], 0
    if fin["noi"] is not None:
        pts += 6
        reasons.append({"text": fin["noiBasis"], "earned": True, "points": 6})
    else:
        reasons.append({"text": "No NOI stated in the documents", "earned": False, "points": 0})
    checks = m["arithmetic_checks"]
    if checks:
        failed = sum(1 for c in checks if c["status"] == "fail")
        warned = sum(1 for c in checks if c["status"] == "warning")
        p = max(0, 6 - 2 * failed - warned)
        pts += p
        reasons.append({"text": f"{len(checks) - failed - warned} of {len(checks)} arithmetic checks verified",
                        "earned": failed == 0 and warned == 0, "points": p})
    else:
        reasons.append({"text": "No stated totals to verify", "earned": False, "points": 0})
    if rows and not m["has_ar_data"]:
        reasons.append({"text": "No receivables data — collections can't be verified", "earned": False, "points": 0})
    elif rows and not m["has_ar_aging"]:
        open_bal = sum(r["arBalance"] for r in rows)
        pts += 3
        reasons.append({"text": f"{money(open_bal)} in open balances, but not aged — can't tell what's past due",
                        "earned": False, "points": 3})
    elif rows:
        delinquent = fin["arDelinquency"]
        share = delinquent / total_rent * 100 if total_rent else 0
        p = 8 if delinquent == 0 else 4 if share <= 10 else 0
        pts += p
        reasons.append({"text": "No 60+ day receivables" if delinquent == 0
                        else f"${delinquent:,.0f} past due 60+ days ({share:.1f}% of annual rent)",
                        "earned": delinquent == 0, "points": p})
    fin_cat = _cat(pts, 20, reasons)

    # 4. Lease leverage (20)
    reasons, pts = [], 0
    walt = m["walt_months"]
    if walt is not None:
        p = 8 if walt >= 60 else 6 if walt >= 36 else 4 if walt >= 24 else 2
        pts += p
        reasons.append({"text": f"WALT {walt:.0f} months ({m['walt_coverage_pct']:.0f}% of rent has a known expiry)",
                        "earned": walt >= 36, "points": p})
    else:
        reasons.append({"text": "WALT can't be calculated — no expiration dates", "earned": False, "points": 0})
    if total_rent:
        covered = sum(r["annualRent"] for r in rows if r["hasLease"]) / total_rent
        p = round(6 * covered, 1)
        pts += p
        reasons.append({"text": f"{covered * 100:.0f}% of rent backed by a lease on file",
                        "earned": covered >= 0.9, "points": p})
    risky = [r for r in rows if r["monthsRemaining"] is None or r["monthsRemaining"] <= NEAR_TERM_MONTHS]
    if rows:
        p = max(0, 6 - 2 * len(risky))
        pts += p
        reasons.append({"text": "No expired, expiring, or undated leases" if not risky
                        else f"{len(risky)} tenant(s) expired, expiring within 12 months, month-to-month, or undated",
                        "earned": not risky, "points": p})
    lease_cat = _cat(pts, 20, reasons)

    # 5. Risk profile (15)
    reasons, pts = [], 0
    vac = fin["vacancy"]
    if vac is not None:
        p = 8 if vac <= 5 else 5 if vac <= 10 else 2 if vac <= 20 else 0
        pts += p
        reasons.append({"text": f"Vacancy {vac:.1f}%", "earned": vac <= 5, "points": p})
    else:
        reasons.append({"text": "Vacancy unknown", "earned": False, "points": 0})
    if rows:
        top_name, share = max(tenant_shares(rows).items(), key=lambda kv: kv[1])
        p = 7 if share <= CONCENTRATION_PCT else 4 if share <= 40 else 1
        pts += p
        reasons.append({"text": f"Largest tenant {top_name} is {share:.0f}% of rent",
                        "earned": share <= CONCENTRATION_PCT, "points": p})
    risk_cat = _cat(pts, 15, reasons)

    # 6. Document coverage + RSF intelligence bonus (15)
    reasons, pts = [], 0
    if documents_uploaded:
        p = round(10 * documents_extracted / documents_uploaded, 1)
        pts += p
        reasons.append({"text": f"{documents_extracted} of {documents_uploaded} documents read and extracted",
                        "earned": documents_extracted == documents_uploaded, "points": p})
    if rsf["alertTriggered"] and rsf["deltaSF"] > 0:
        pts += 5
        reasons.append({"text": "RSF recovery opportunity identified (BOMA vs rent roll over 5%)",
                        "earned": True, "points": 5})
    cov_cat = _cat(pts, 15, reasons)

    categories = {
        "dataCompleteness": data, "rsfAlignment": rsf_cat, "financialIntegrity": fin_cat,
        "leaseLeverage": lease_cat, "riskProfile": risk_cat, "documentCoverage": cov_cat,
    }
    overall = round(min(100, sum(c["points"] for c in categories.values())))
    tier, readiness = tier_for(overall)
    return {"overall": overall, "tier": tier, "dealReadiness": readiness, "categories": categories}


def tenant_shares(rows: list[dict]) -> dict[str, float]:
    """Share of rent per tenant, adding up tenants that lease more than one suite."""
    names: dict[str, str] = {}
    shares: dict[str, float] = {}
    for r in rows:
        key = tenant_key(r["name"])
        names.setdefault(key, r["name"])
        shares[key] = shares.get(key, 0) + r["incomeConcentration"]
    return {names[k]: round(v, 1) for k, v in shares.items()}


def tier_for(score: float) -> tuple[str, str]:
    if score >= 80:
        return "GREEN", "Proceed with confidence"
    if score >= 60:
        return "YELLOW", "Proceed with conditions"
    if score >= 40:
        return "ORANGE", "Material gaps"
    return "RED", "Insufficient data"


# ── Red flags and requests ───────────────────────────────────────────────────

def computed_red_flags(m: dict) -> list[dict]:
    flags: list[dict] = []
    rows = m["tenants"]
    total_rent = m["financial"]["totalAnnualRent"]
    rsf = m["rsf_reconciliation"]

    def add(severity, category, description, impact, resolution):
        flags.append({"severity": severity, "category": category, "description": description,
                      "impact": impact, "resolution": resolution, "source": "computed"})

    if rsf["comparable"] and abs(rsf["deltaPercent"]) > RSF_NOTICE_PCT:
        over = rsf["deltaSF"] > 0
        add("HIGH" if rsf["alertTriggered"] else "MEDIUM", "RSF Discrepancy",
            f"BOMA ({rsf['bomaTotalSF']:,.0f} SF) {'exceeds' if over else 'is below'} the "
            f"{rsf['occupiedSource'] or 'rent roll'} ({rsf['rentRollOccupiedSF']:,.0f} SF) by {abs(rsf['deltaSF']):,.0f} SF "
            f"({abs(rsf['deltaPercent']):.1f}%)",
            (_recovery_text(rsf) if over and rsf["estimatedAnnualRecovery"]
             else "Tenants may be billed on more area than was measured"),
            "Confirm which measurement the leases reference; request remeasurement or adjust pricing")

    # Group suites by tenant so a tenant in three suites gets one flag, not three.
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(tenant_key(r["name"]), []).append(r)

    def where(g: list[dict]) -> str:
        return ", ".join(suite_label(r["suite"]) for r in g)

    mtm, undated, lapsed = [], [], []
    data_as_of = m.get("data_as_of")
    for g in groups.values():
        name = g[0]["name"]
        pct = sum(r["incomeConcentration"] for r in g)
        share = f"{pct:.0f}% of rent"
        if all(r["monthToMonth"] for r in g):
            mtm.append((name, pct))
        elif any(r["monthsRemaining"] is None and not r["monthToMonth"] for r in g):
            undated.append(name)
            add("HIGH", "Missing Expiry", f"{name} ({where(g)}) has no documented expiration",
                f"Rollover risk can't be assessed for {share}",
                f"Request the executed lease and any amendments for {name}")
        else:
            dated = [r for r in g if r["monthsRemaining"] is not None]
            soonest = min(dated, key=lambda r: r["monthsRemaining"]) if dated else None
            if soonest and soonest["monthsRemaining"] < 0 and data_as_of and soonest["leaseExpiry"] > data_as_of:
                lapsed.append((name, soonest["leaseExpiry"], pct))
            elif soonest and soonest["monthsRemaining"] < 0:
                add("HIGH", "Expired Lease",
                    f"{name} lease expired {soonest['leaseExpiry']} ({abs(soonest['monthsRemaining'])} months ago)",
                    f"{share} may be month-to-month or holding over",
                    f"Request any renewal or extension for {name}, or price in the vacancy")
            elif soonest and soonest["monthsRemaining"] <= NEAR_TERM_MONTHS:
                add("MEDIUM", "Near-term Expiry",
                    f"{name} expires {soonest['leaseExpiry']} ({soonest['monthsRemaining']} months)",
                    f"{share} rolls within a year of today",
                    f"Ask about renewal status with {name}")
        over60 = sum(r["arOver60"] for r in g)
        if any(r["arStatus"] == "DELINQUENT" for r in g):
            note = next((f" — {r['arNote']}" for r in g if r.get("arNote")), "")
            add("HIGH" if over60 >= sum(r["monthlyRent"] for r in g) else "MEDIUM", "AR Delinquency",
                f"{name} has ${over60:,.0f} past due 60+ days{note}",
                f"Collection risk on {share}",
                "Request payment history and confirm the balance with management")
        if pct > CONCENTRATION_PCT and total_rent:
            add("MEDIUM", "Tenant Concentration",
                f"{name} pays {share}" + (f" across {len(g)} suites" if len(g) > 1 else ""),
                "Loss of this tenant would materially cut income",
                f"Review {name}'s credit, guarantor, and renewal options")

    if lapsed:
        lapsed.sort(key=lambda t: t[1])
        names = ", ".join(f"{n} ({e})" for n, e, _ in lapsed[:6]) + (f" and {len(lapsed) - 6} more" if len(lapsed) > 6 else "")
        add("HIGH", "Expired Since Report",
            f"{len(lapsed)} lease(s) ran out after the {data_as_of} report: {names}",
            f"{sum(p for _, _, p in lapsed):.0f}% of rent — renewed, holding over, or gone is unknown",
            "Request a current rent roll and any renewals signed since the report")
    if mtm:
        mtm.sort(key=lambda t: -t[1])
        names = ", ".join(n for n, _ in mtm[:6]) + (f" and {len(mtm) - 6} more" if len(mtm) > 6 else "")
        add("MEDIUM", "Month-to-Month",
            f"{len(mtm)} tenant(s) are month-to-month: {names}",
            f"{sum(p for _, p in mtm):.0f}% of rent can leave on 30 days' notice",
            "Ask which are negotiating renewals; price these as near-term rollover")
    audit = m.get("lease_audit") or {}
    summ = audit.get("summary") or {}
    under = [a for a in audit.get("tenants", []) if a["deltaSF"] and a["deltaSF"] > 0
             and a["deltaPct"] > lease_audit.MATERIAL_PCT]
    if under:
        open_dollars = (summ.get("collectibleUpside") or 0) + (summ.get("pendingUpside") or 0)
        under.sort(key=lambda a: -(a["totalGap"] or 0))
        detail = "; ".join(f"{a['name']} {a['billedRsf']:,.0f} vs {a['bomaRsf']:,.0f} SF" for a in under[:5])
        calls = summ.get("leverage") or {}
        lever = ", ".join(f"{n} {LEVERAGE_WORDS[c]}" for c, n in calls.items() if c in LEVERAGE_WORDS)
        dollars = (f"${summ['totalUpside']:,.0f}/yr" + (f" (${summ['baseRentUpside']:,.0f} base rent + "
                   f"${summ['camUpside']:,.0f} CAM)" if summ.get("camUpside") else " in base rent")
                   if summ.get("totalUpside") else f"{summ['underbilledSF']:,.0f} SF")
        add("HIGH" if open_dollars > 25000 else "MEDIUM", "Suite Area Underbilled",
            f"{len(under)} suite(s) billed on {summ['underbilledSF']:,.0f} SF less than BOMA measured: {detail}",
            f"{dollars} not collected" + (f". Leverage: {lever}" if lever else ""),
            "See the Lease Audit tab for each lease's remeasurement terms; correct the area where the lease allows "
            "it and price the rest into renewals")
    over_t = [a for a in audit.get("tenants", []) if a["leverage"]["call"] == "OVERBILLED"]
    if over_t:
        detail = "; ".join(f"{a['name']} {a['billedRsf']:,.0f} vs {a['bomaRsf']:,.0f} SF" for a in over_t[:5])
        add("MEDIUM", "Tenant Overbilled",
            f"{len(over_t)} tenant(s) billed on more area than BOMA measured: {detail}",
            (f"About ${summ['overbilledExposure']:,.0f}/yr a tenant could claim back" if summ.get("overbilledExposure")
             else "A tenant could claim a refund or a rent reduction"),
            "Price the reduction in, or get estoppels confirming the billed area")

    for c in m["expiry_conflicts"]:
        add("MEDIUM", "Expiry Conflict",
            f"{c['tenant']}: lease says {c['lease_end']}, rent roll says {c['rent_roll_end']}",
            "WALT and rollover depend on which date is right",
            "Confirm with the latest amendment or a tenant estoppel")
    for o in m["orphan_leases"]:
        add("LOW", "Lease Not on Rent Roll", f"Lease for {o['tenant'] or 'a tenant'} ({o['file']}) has no rent roll row",
            "May be a former tenant or a missing rent roll entry", "Confirm whether this tenant is in occupancy")
    for c in m["arithmetic_checks"]:
        if c["status"] == "pass":
            continue
        if c.get("kind") == "billing":
            add("HIGH" if c["status"] == "fail" else "MEDIUM", "Contract vs Billed Rent", c["detail"],
                "Could be free rent, abatements, percentage-rent tenants, or tenants not being billed",
                "Ask management to tie each lease's contract rent to what was billed and collected")
        elif c["status"] == "fail":
            add("MEDIUM", "Arithmetic Mismatch", f"{c['label']}: {c['detail']}",
                f"Figures in {c['source']} don't add up", "Ask management to reconcile the stated figure")
    age = m.get("data_age_months")
    if age is not None and age > STALE_MONTHS:
        add("MEDIUM", "Stale Data", f"The rent roll / management report is dated {m['data_as_of']} ({age} months old)",
            "Tenants, balances, and vacancy may have changed since", "Request a current rent roll and AR aging")
    if m.get("landlord_use"):
        spaces = ", ".join(f"{x['name']} ({suite_label(x['suite'])})" for x in m["landlord_use"][:5])
        add("LOW", "Landlord-Use Space", f"Not counted as tenants or vacancy: {spaces}",
            "These spaces earn no rent; check whether any could be leased", "Confirm their area and use with management")
    for f in m["failed_extractions"]:
        add("LOW", "Unread Document", f"{f['filename']} could not be extracted",
            "Its data is missing from this analysis", "Re-upload a clearer or text-based copy")

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    flags.sort(key=lambda f: order[f["severity"]])
    return flags


LEVERAGE_WORDS = {"STRONG": "can be remeasured", "NEGOTIABLE": "negotiable", "NONE": "locked by the lease",
                  "NO_LEASE": "no lease on file"}


def _recovery_text(rsf: dict) -> str:
    base, cam = rsf.get("baseRentRecovery") or 0, rsf.get("camRecovery") or 0
    if cam:
        return (f"About ${rsf['estimatedAnnualRecovery']:,.0f}/yr may not be billed: ${base:,.0f} base rent at "
                f"${rsf['averageRentPSF']:.2f}/SF plus ${cam:,.0f} CAM at ${rsf['camRatePSF']:.2f}/SF")
    return (f"About ${rsf['estimatedAnnualRecovery']:,.0f}/yr may not be billed at the average rent of "
            f"${rsf['averageRentPSF']:.2f}/SF")


def what_to_get_next(m: dict, synthesis_items: list[Any]) -> list[str]:
    present = set(m["present_types"])
    items: list[str] = []
    audit_lease = {tenant_key(a["name"]) for a in (m.get("lease_audit") or {}).get("tenants", [])
                   if a["leverage"]["call"] == "NO_LEASE"}
    asked: set[str] = set()
    for r in m["tenants"]:
        key = tenant_key(r["name"])
        if r["monthsRemaining"] is None and not r["monthToMonth"] and key not in asked and key not in audit_lease:
            asked.add(key)
            items.append(f"Executed lease for {r['name']} — no expiration on file ({r['incomeConcentration']:.0f}% of rent)")
    seen = {tenant_key(r["name"]) for r in m["tenants"] if r["monthsRemaining"] is None and not r["monthToMonth"]}
    audit = m.get("lease_audit") or {}
    need_lease = [a for a in audit.get("tenants", []) if a["leverage"]["call"] == "NO_LEASE"]
    if need_lease:
        need_lease.sort(key=lambda a: -(a["totalGap"] or 0))
        names = ", ".join(a["name"] for a in need_lease[:4]) + (" and others" if len(need_lease) > 4 else "")
        money_at = sum(a["totalGap"] or 0 for a in need_lease)
        undated = [a["name"] for a in need_lease if tenant_key(a["name"]) in seen]
        items.append(f"Leases for {names} — their remeasurement terms decide whether "
                     f"{f'${money_at:,.0f}/yr' if money_at else 'the area gap'} can be collected"
                     + (f" ({', '.join(undated)} also has no expiration on file)" if undated else ""))
    if audit.get("available") and "CAM_RECONCILIATION" not in present:
        items.append("Last year's CAM reconciliation — the exact expense pool and each tenant's billed share")
    if any(r["monthToMonth"] for r in m["tenants"]):
        items.append("Status of month-to-month tenants — who is renewing, who is leaving")
    for key, label, types in CORE_DOC_GROUPS:
        has = bool(present & set(types)) or (key == "rent_roll" and m["has_rent_roll"])
        if not has:
            items.append(f"{label} — {DOC_REQUEST_REASONS[key]}")
    no_lease = [r["name"] for r in m["tenants"] if not r["hasLease"] and r["monthsRemaining"] is not None]
    if no_lease and not need_lease and ("LEASE" in present or "LEASE_ABSTRACT" in present):
        items.append(f"Leases for {', '.join(no_lease[:4])}{' and others' if len(no_lease) > 4 else ''}")
    if m["tenants"] and not m["has_ar_aging"]:
        items.append("AR aging report — shows which balances are 30, 60, 90+ days past due")

    for item in synthesis_items or []:
        if isinstance(item, dict):
            doc, why = text(item.get("document")), text(item.get("why_needed"))
            line = f"{doc} — {why}" if doc and why else doc
        else:
            line = text(item)
        if line and not any(_similar(line, existing) for existing in items):
            items.append(line)
    return items[:8]


def _similar(a: str, b: str) -> bool:
    return names_match(a.split("—")[0], b.split("—")[0])


# ── Report assembly ──────────────────────────────────────────────────────────

_TYPE_ALIASES = {"RENT_ROLL_XLSX": "RENT_ROLL"}


def _expense_label(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    low = s.lower()
    if "modif" in low:
        return "MODIFIED_GROSS"
    if "gross" in low or "full service" in low:
        return "GROSS"
    if "nnn" in low or "triple" in low or "net" in low:
        return "NNN"
    return None


def expiry_schedule(rows: list[dict], today: date, years: int = 6) -> list[dict]:
    buckets = [{"label": "Expired", "annualRent": 0.0, "tenants": []}]
    buckets += [{"label": str(today.year + i), "annualRent": 0.0, "tenants": []} for i in range(years)]
    buckets.append({"label": f"{today.year + years}+", "annualRent": 0.0, "tenants": []})
    buckets.append({"label": "Unknown", "annualRent": 0.0, "tenants": []})
    for r in rows:
        if r["leaseExpiry"] is None:
            b = buckets[-1]
        else:
            exp = date.fromisoformat(r["leaseExpiry"])
            if exp < today:
                b = buckets[0]
            elif exp.year - today.year >= years:
                b = buckets[-2]
            else:
                b = buckets[1 + exp.year - today.year]
        b["annualRent"] += r["annualRent"]
        b["tenants"].append(r["name"])
    for b in buckets:
        b["annualRent"] = round(b["annualRent"], 2)
    return buckets


def build_report(*, deal_id: str, deal_name: str, classified_documents: list[dict],
                 extractions: list[dict], ingest_errors: list[str], metrics: dict,
                 synthesis: Optional[dict], pipeline_errors: list[str],
                 files_uploaded: int, completed_at: str) -> dict:
    """Assemble the dashboard payload (matches the frontend DealAnalysis type)."""
    m = metrics
    synthesis = synthesis or {}
    extracted_ok = sum(1 for e in extractions if not e.get("parse_error") and e.get("extraction"))
    # Files that turned out not to be deal documents don't count against coverage; unreadable ones do.
    skipped = sum(1 for d in classified_documents if d["doc_type"] == "OTHER")
    score = score_deal(m, max(files_uploaded - skipped, extracted_ok), extracted_ok)

    flags = computed_red_flags(m)
    for f in synthesis.get("red_flags") or []:
        sev = str(f.get("severity", "MEDIUM")).upper()
        flags.append({
            "severity": "HIGH" if sev in ("CRITICAL", "HIGH") else "LOW" if sev == "LOW" else "MEDIUM",
            "category": text(f.get("category")) or "AI review",
            "description": text(f.get("description")) or text(f.get("flag")) or "",
            "impact": text(f.get("impact")) or "",
            "resolution": text(f.get("resolution")),
            "source": "ai_review",
            "sourceDocuments": f.get("source_documents") or [],
        })
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    flags.sort(key=lambda f: (order[f["severity"]], f["source"] != "computed"))
    for i, f in enumerate(flags):
        f["id"] = f"rf-{i + 1}"

    lease_abstracts = []
    for i, l in enumerate(m["leases"]):
        lease_abstracts.append({
            "id": f"la-{i + 1}",
            "tenantName": l.tenant_name or "Unknown tenant",
            "suite": l.suite or "",
            "rsf": l.rsf or 0,
            "commencementDate": l.start.isoformat() if l.start else None,
            "expirationDate": l.end.isoformat() if l.end else None,
            "baseRent": l.annual_rent or ((l.monthly_rent or 0) * 12),
            "escalation": l.escalation or "Unknown",
            "expenseStructure": _expense_label(l.expense_structure),
            "expenseStructureText": l.expense_structure,
            "camCap": l.cam_cap,
            "renewalOptions": l.renewal_options,
            "tiAllowance": l.ti_allowance,
            "remeasurementRights": bool(l.remeasurement_rights and
                                        l.remeasurement_rights.lower() not in ("none", "no", "n/a")),
            "missingFields": l.missing_fields,
            "confidence": l.confidence,
            "sourceFile": l.filename,
        })

    extraction_by_doc = {e["doc_id"]: e for e in extractions}
    documents = []
    for d in classified_documents:
        e = extraction_by_doc.get(d["doc_id"])
        if d["doc_type"] == "OTHER":
            status, note = "SKIPPED", "Not a supported document type"
        elif e and not e.get("parse_error") and e.get("extraction"):
            status, note = "PROCESSED", "Truncated — very long document" if e.get("truncated") else None
        else:
            status, note = "FAILED", (e or {}).get("parse_error") or "Extraction failed"
        documents.append({
            "id": d["doc_id"], "filename": d["filename"],
            "type": _TYPE_ALIASES.get(d["doc_type"], d["doc_type"]),
            "classificationConfidence": d.get("classification_confidence"),
            "uploadedAt": completed_at, "pageCount": d.get("page_count") or 1,
            "ocr": bool(d.get("ocr_performed")), "status": status, "note": note,
        })
    for err in ingest_errors:
        name, _, reason = err.partition(": ")
        documents.append({"id": f"err-{len(documents)}", "filename": name, "type": "OTHER",
                          "classificationConfidence": None, "uploadedAt": completed_at, "pageCount": 0,
                          "ocr": False, "status": "FAILED", "note": reason})

    fin = m["financial"]
    return {
        "id": deal_id,
        "dealName": deal_name,
        "propertyAddress": text(synthesis.get("property_address")) or m["property_address"] or "",
        "submittedAt": completed_at,
        "asOf": m["as_of"],
        "dataAsOf": m["data_as_of"],
        "dataAgeMonths": m["data_age_months"],
        "landlordUseSpaces": m["landlord_use"],
        "score": score["overall"],
        "tier": score["tier"],
        "dealReadiness": score["dealReadiness"],
        "subScores": {k: v["points"] for k, v in score["categories"].items()},
        "scoreBreakdown": score["categories"],
        "executiveSummary": text(synthesis.get("executive_summary")),
        "rsfReconciliation": m["rsf_reconciliation"],
        "leaseAudit": m["lease_audit"],
        "financialSummary": fin,
        "walt": m["walt_months"],
        "waltCoverage": m["walt_coverage_pct"],
        "buildingRsf": m["building_rsf"],
        "vacantRsf": m["vacant_rsf"],
        "redFlags": flags,
        "whatToGetNext": what_to_get_next(m, synthesis.get("what_to_get_next") or []),
        "tenants": m["tenants"],
        "leaseAbstracts": lease_abstracts,
        "documents": documents,
        "arithmeticChecks": m["arithmetic_checks"],
        "expirySchedule": expiry_schedule(m["tenants"], date.fromisoformat(m["as_of"])),
        "pipelineErrors": pipeline_errors,
        "isSample": False,
    }


def public_metrics(m: dict) -> dict:
    """Metrics without internal objects, safe to send to the model or serialize."""
    out = {k: v for k, v in m.items() if not k.startswith("_") and k != "leases"}
    out["leases"] = [{"tenant": l.tenant_name, "suite": l.suite, "rsf": l.rsf, "expires": l.end,
                      "annual_rent": l.annual_rent, "file": l.filename} for l in m["leases"]]
    return out
