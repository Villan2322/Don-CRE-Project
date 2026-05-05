from .base import BaseAgent


RISK_SCORING_PROMPT = """You are an expert commercial real estate deal risk scoring agent.
Your job is to analyze all available data and produce a comprehensive deal score (0-100).

Scoring Categories (weights):
1. Document Completeness (15%)
   - 100: All required docs present
   - 75: Minor docs missing
   - 50: Some key docs missing
   - 25: Critical docs missing

2. RSF Integrity (20%)
   - 100: All sources match within 1%
   - 75: Minor variances (1-3%)
   - 50: Moderate variances (3-5%)
   - 25: Significant variances (>5%)

3. Lease Quality (20%)
   - Consider: WALT, tenant credit, renewal options, escalations
   - 100: Strong WALT (>5yr), credit tenants, good escalations
   - Lower scores for short-term leases, weak tenants

4. Income Verification (15%)
   - 100: All rents verified to leases, current collections
   - Deduct for AR aging, rent discrepancies

5. Expense Analysis (10%)
   - 100: Clear expense structure, CAM reconciled
   - Deduct for unclear reimbursements, missing reconciliations

6. Red Flag Severity (20%)
   - 100: No red flags
   - Deduct based on count and severity of issues

Deal Tier based on score:
- 80-100: GREEN (Proceed with confidence) - Low risk, documentation complete
- 60-79: YELLOW (Proceed with conditions) - Some items to address before closing
- 40-59: ORANGE (Material gaps) - Significant issues require resolution
- 0-39: RED (Insufficient data) - Critical concerns, do not proceed

Return your analysis as JSON:
{
  "deal_score": {
    "overall_score": 78,
    "tier": "YELLOW",
    "deal_readiness": "Proceed with conditions",
    "sub_scores": {
      "document_completeness": 85,
      "rsf_integrity": 65,
      "lease_quality": 82,
      "income_verification": 90,
      "expense_analysis": 75,
      "red_flag_impact": 70
    }
  },
  "score_factors": [
    {
      "category": "rsf_integrity",
      "impact": -15,
      "reason": "3.2% variance between rent roll and BOMA measurements"
    },
    {
      "category": "lease_quality",
      "impact": -8,
      "reason": "WALT of 3.1 years below target of 5 years"
    }
  ],
  "recommendations": [
    "Request updated BOMA measurement before closing",
    "Negotiate tenant renewal commitments",
    "Verify AR aging with management"
  ]
}"""


class RiskScoringAgent(BaseAgent):
    """Agent specialized in comprehensive deal risk scoring."""
    
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
        """Generate comprehensive deal score."""
        deal_data = {
            "documents": documents_status,
            "rsf_reconciliation": rsf_reconciliation,
            "leases": lease_abstracts,
            "rent_roll": rent_roll_analysis,
            "red_flags": red_flags
        }
        
        content = f"Complete deal data for scoring:\n{deal_data}"
        return await self.analyze(content)
