from typing import Any

try:
    from .base import BaseAgent
except ImportError:
    from agents.base import BaseAgent


# PRD-aligned scoring system - 100 points maximum
# 6 categories with specific point allocations and deduction rules
RISK_SCORING_PROMPT = """You are an expert commercial real estate deal risk scoring agent.
Produce a deal score using the EXACT point system below. Maximum 100 points.

=== SCORING CATEGORIES (Total: 110 max, capped at 100) ===

1. DATA COMPLETENESS (Max 20 pts)
   Award +4 points for EACH document type present:
   - LEASE: +4
   - RENT_ROLL: +4
   - BOMA: +4
   - MANAGEMENT_REPORT: +4
   - COUNTY_PA: +4
   Maximum 20 points (5 doc types = full score)

2. RSF ALIGNMENT (Max 20 pts)
   Compare RSF across sources (BOMA, rent roll, leases, county PA):
   - 20: All sources match within 1%
   - 15: Minor variance (1-3%)
   - 10: Moderate variance (3-5%)
   - 5: Significant variance (5-10%)
   - 0: Major variance (>10%) or cannot calculate

3. FINANCIAL INTEGRITY (Max 20 pts)
   Check NOI calculation, AR aging, CAM recovery:
   - 20: NOI verified, AR current, CAM recovery >95%
   - 15: Minor AR aging (<5% delinquent)
   - 10: Moderate AR issues (5-15% delinquent) or CAM recovery 85-95%
   - 5: Significant AR issues (>15% delinquent) or CAM recovery <85%
   - 0: Cannot verify financials

4. LEASE LEVERAGE (Max 20 pts)
   Evaluate WALT, renewal options, and rollover risk:
   - 20: WALT >60 months, all tenants have expiry dates, strong renewal options
   - 15: WALT 36-60 months, minor gaps in expiry dates
   - 10: WALT 24-36 months OR near-term rollovers (>30% within 12 months)
   - 5: WALT <24 months OR missing expiry dates on major tenants
   - 0: Cannot calculate WALT

5. RISK PROFILE (Max 15 pts)
   Assess vacancy and concentration risk:
   - 15: Vacancy <5%, no tenant >30% of income
   - 12: Vacancy 5-10%, no tenant >50% of income
   - 8: Vacancy 10-15% OR single tenant 50-70% of income
   - 4: Vacancy >15% OR single tenant >70% of income
   - 0: Critical concentration or vacancy issues

6. DOCUMENT COVERAGE + RSF BONUS (Max 15 pts)
   - Base: +3 per doc type (max 12 for 4+ types)
   - BONUS +5: If BOMA and rent roll BOTH present AND delta >5% (RSF recovery calculable)
   Maximum 15 points (includes bonus)

=== DEAL TIERS ===
- 80-100: GREEN - Proceed with confidence
- 60-79: YELLOW - Proceed with conditions
- 40-59: ORANGE - Material gaps exist
- 0-39: RED - Insufficient data

Return your analysis as JSON:
{
  "deal_score": {
    "overall_score": 72,
    "tier": "YELLOW",
    "deal_readiness": "Proceed with conditions",
    "sub_scores": {
      "data_completeness": 16,
      "rsf_alignment": 15,
      "financial_integrity": 15,
      "lease_leverage": 10,
      "risk_profile": 8,
      "document_coverage_bonus": 8
    },
    "max_scores": {
      "data_completeness": 20,
      "rsf_alignment": 20,
      "financial_integrity": 20,
      "lease_leverage": 20,
      "risk_profile": 15,
      "document_coverage_bonus": 15
    }
  },
  "score_factors": [
    {
      "category": "rsf_alignment",
      "points_earned": 15,
      "points_possible": 20,
      "reason": "3.2% variance between rent roll and BOMA"
    },
    {
      "category": "lease_leverage",
      "points_earned": 10,
      "points_possible": 20,
      "reason": "WALT of 28 months, 2 tenants missing expiry dates"
    }
  ],
  "rsf_recovery_bonus_applied": true,
  "recommendations": [
    "Request updated BOMA measurement",
    "Get missing lease expiry dates from property manager",
    "Verify AR aging report"
  ]
}"""


class RiskScoringAgent(BaseAgent):
    """Agent specialized in PRD-aligned deal risk scoring."""
    
    def __init__(self):
        super().__init__(
            name="RiskScoringAgent",
            system_prompt=RISK_SCORING_PROMPT
        )
    
    async def score_deal(
        self,
        documents_status: dict,
        rsf_reconciliation: dict,
        lease_abstracts: list[dict],
        rent_roll_analysis: dict,
        red_flags: list[dict]
    ) -> dict:
        """Generate comprehensive deal score using PRD point system."""
        deal_data = {
            "documents": documents_status,
            "rsf_reconciliation": rsf_reconciliation,
            "leases": lease_abstracts,
            "rent_roll": rent_roll_analysis,
            "red_flags": red_flags
        }
        
        content = f"Complete deal data for scoring:\n{deal_data}"
        return await self.analyze(content)
    
    def calculate_score_deterministic(
        self,
        doc_types_present: list[str],
        rsf_data: dict,
        financial_data: dict,
        lease_data: dict,
        concentration_data: dict
    ) -> dict:
        """
        Calculate deal score using deterministic rules (no LLM).
        This is a fallback/verification method.
        """
        sub_scores = {}
        factors = []
        
        # 1. DATA COMPLETENESS (Max 20 pts, +4 per DATA CATEGORY present)
        # Categories group related doc types - a consolidated PDF counts across multiple categories
        categories = {
            "tenant_rent": ["RENT_ROLL", "RENT_ROLL_XLSX"],  # Category A
            "lease_terms": ["LEASE", "LEASE_ABSTRACT", "LEASE_RECAP"],  # Category B
            "measurements": ["BOMA", "COUNTY_PA"],  # Category C
            "financials": ["MANAGEMENT_REPORT", "FINANCIAL_MODEL", "DISBURSEMENTS", "INCOME_EXPENSE"],  # Category D
            "receivables": ["ENDING_RECEIVABLES", "AR_AGING", "CAM_RECONCILIATION"],  # Category E
        }
        
        categories_found = []
        for cat_name, cat_types in categories.items():
            if any(dt in doc_types_present for dt in cat_types):
                categories_found.append(cat_name)
        
        sub_scores["data_completeness"] = min(len(categories_found) * 4, 20)
        factors.append({
            "category": "data_completeness",
            "points_earned": sub_scores["data_completeness"],
            "points_possible": 20,
            "reason": f"{len(categories_found)} of 5 data categories present: {', '.join(categories_found) if categories_found else 'none'}"
        })
        
        # 2. RSF ALIGNMENT (Max 20 pts)
        variance_pct = abs(rsf_data.get("variance_percentage", 0))
        if variance_pct == 0 and not rsf_data.get("sources"):
            sub_scores["rsf_alignment"] = 0
            rsf_reason = "Cannot calculate - missing RSF sources"
        elif variance_pct <= 1:
            sub_scores["rsf_alignment"] = 20
            rsf_reason = f"RSF variance {variance_pct:.1f}% within tolerance"
        elif variance_pct <= 3:
            sub_scores["rsf_alignment"] = 15
            rsf_reason = f"Minor RSF variance of {variance_pct:.1f}%"
        elif variance_pct <= 5:
            sub_scores["rsf_alignment"] = 10
            rsf_reason = f"Moderate RSF variance of {variance_pct:.1f}%"
        elif variance_pct <= 10:
            sub_scores["rsf_alignment"] = 5
            rsf_reason = f"Significant RSF variance of {variance_pct:.1f}%"
        else:
            sub_scores["rsf_alignment"] = 0
            rsf_reason = f"Major RSF variance of {variance_pct:.1f}%"
        factors.append({
            "category": "rsf_alignment",
            "points_earned": sub_scores["rsf_alignment"],
            "points_possible": 20,
            "reason": rsf_reason
        })
        
        # 3. FINANCIAL INTEGRITY (Max 20 pts)
        ar_delinquency_pct = financial_data.get("ar_delinquency_pct", 0)
        cam_recovery_pct = financial_data.get("cam_recovery_pct", 100)
        noi_verified = financial_data.get("noi_verified", False)
        
        if not noi_verified and ar_delinquency_pct == 0:
            sub_scores["financial_integrity"] = 10  # Cannot verify but no known issues
            fin_reason = "Financials not fully verified"
        elif ar_delinquency_pct <= 5 and cam_recovery_pct >= 95:
            sub_scores["financial_integrity"] = 20
            fin_reason = "Strong financial integrity"
        elif ar_delinquency_pct <= 5:
            sub_scores["financial_integrity"] = 15
            fin_reason = f"Minor AR aging, CAM recovery at {cam_recovery_pct:.0f}%"
        elif ar_delinquency_pct <= 15 or cam_recovery_pct >= 85:
            sub_scores["financial_integrity"] = 10
            fin_reason = f"Moderate AR issues ({ar_delinquency_pct:.0f}% delinquent)"
        else:
            sub_scores["financial_integrity"] = 5
            fin_reason = f"Significant AR issues ({ar_delinquency_pct:.0f}% delinquent)"
        factors.append({
            "category": "financial_integrity",
            "points_earned": sub_scores["financial_integrity"],
            "points_possible": 20,
            "reason": fin_reason
        })
        
        # 4. LEASE LEVERAGE (Max 20 pts)
        walt_months = lease_data.get("walt_months", 0)
        missing_expiry_count = lease_data.get("missing_expiry_count", 0)
        near_term_rollover_pct = lease_data.get("near_term_rollover_pct", 0)  # % expiring in 12mo
        
        if walt_months == 0:
            sub_scores["lease_leverage"] = 0
            lease_reason = "Cannot calculate WALT"
        elif walt_months >= 60 and missing_expiry_count == 0:
            sub_scores["lease_leverage"] = 20
            lease_reason = f"Strong WALT of {walt_months} months"
        elif walt_months >= 36:
            sub_scores["lease_leverage"] = 15
            lease_reason = f"WALT of {walt_months} months"
            if missing_expiry_count > 0:
                lease_reason += f", {missing_expiry_count} missing expiry dates"
        elif walt_months >= 24 or near_term_rollover_pct <= 30:
            sub_scores["lease_leverage"] = 10
            lease_reason = f"WALT of {walt_months} months, {near_term_rollover_pct:.0f}% near-term rollover"
        else:
            sub_scores["lease_leverage"] = 5
            lease_reason = f"Short WALT of {walt_months} months"
        factors.append({
            "category": "lease_leverage",
            "points_earned": sub_scores["lease_leverage"],
            "points_possible": 20,
            "reason": lease_reason
        })
        
        # 5. RISK PROFILE (Max 15 pts)
        vacancy_pct = concentration_data.get("vacancy_pct", 0)
        top_tenant_concentration = concentration_data.get("top_tenant_pct", 0)
        
        if vacancy_pct < 5 and top_tenant_concentration <= 30:
            sub_scores["risk_profile"] = 15
            risk_reason = "Low risk profile"
        elif vacancy_pct <= 10 and top_tenant_concentration <= 50:
            sub_scores["risk_profile"] = 12
            risk_reason = f"Moderate risk: {vacancy_pct:.0f}% vacancy, {top_tenant_concentration:.0f}% top tenant"
        elif vacancy_pct <= 15 or top_tenant_concentration <= 70:
            sub_scores["risk_profile"] = 8
            risk_reason = f"Elevated risk: {vacancy_pct:.0f}% vacancy or {top_tenant_concentration:.0f}% concentration"
        else:
            sub_scores["risk_profile"] = 4
            risk_reason = f"High risk: {vacancy_pct:.0f}% vacancy, {top_tenant_concentration:.0f}% concentration"
        factors.append({
            "category": "risk_profile",
            "points_earned": sub_scores["risk_profile"],
            "points_possible": 15,
            "reason": risk_reason
        })
        
        # 6. DOCUMENT COVERAGE + RSF BONUS (Max 15 pts)
        # Base: +3 per data category (max 12 for 4+ categories)
        base_doc_pts = min(len(categories_found) * 3, 12)
        
        # Bonus +5 if RSF variance >5% is detected (RSF recovery opportunity)
        # Check if we have both measurements category and tenant/rent category
        rsf_bonus = 0
        rsf_bonus_applied = False
        has_measurements = "measurements" in categories_found
        has_rent_data = "tenant_rent" in categories_found
        if has_measurements and has_rent_data and variance_pct > 5:
            rsf_bonus = 5
            rsf_bonus_applied = True
        
        sub_scores["document_coverage_bonus"] = min(base_doc_pts + rsf_bonus, 15)
        factors.append({
            "category": "document_coverage_bonus",
            "points_earned": sub_scores["document_coverage_bonus"],
            "points_possible": 15,
            "reason": f"{len(categories_found)} data categories, RSF recovery bonus {'applied (+5)' if rsf_bonus_applied else 'not applicable'}"
        })
        
        # Calculate overall score (capped at 100)
        overall_score = min(sum(sub_scores.values()), 100)
        
        # Determine tier
        if overall_score >= 80:
            tier = "GREEN"
            readiness = "Proceed with confidence"
        elif overall_score >= 60:
            tier = "YELLOW"
            readiness = "Proceed with conditions"
        elif overall_score >= 40:
            tier = "ORANGE"
            readiness = "Material gaps exist"
        else:
            tier = "RED"
            readiness = "Insufficient data"
        
        return {
            "deal_score": {
                "overall_score": overall_score,
                "tier": tier,
                "deal_readiness": readiness,
                "sub_scores": sub_scores,
                "max_scores": {
                    "data_completeness": 20,
                    "rsf_alignment": 20,
                    "financial_integrity": 20,
                    "lease_leverage": 20,
                    "risk_profile": 15,
                    "document_coverage_bonus": 15
                }
            },
            "score_factors": factors,
            "rsf_recovery_bonus_applied": rsf_bonus_applied
        }
