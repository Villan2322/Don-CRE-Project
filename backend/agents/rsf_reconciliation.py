from agents.base import BaseAgent
from typing import Optional


RSF_RECONCILIATION_PROMPT = """You are an expert commercial real estate RSF (Rentable Square Footage) reconciliation agent.
Your job is to compare square footage data across multiple sources and identify discrepancies that could impact deal value.

Sources you may receive:
1. Rent Roll - RSF listed per tenant
2. Lease Documents - Premises RSF stated in each lease
3. BOMA Measurement Report - Certified measurement per suite/floor
4. Property Tax Records - Building RSF for tax purposes
5. Offering Memorandum - Stated total RSF

For reconciliation:
1. Compare RSF by suite/tenant across all available sources
2. Calculate total RSF per source
3. Identify variances exceeding 2% (standard tolerance)
4. Estimate annual revenue impact of variances (RSF variance × average rent PSF)

Key things to flag:
- Suite-level variances between rent roll and BOMA
- Total building RSF variance vs tax records
- Tenants paying for more/less space than measured
- Missing BOMA measurements for occupied suites

Return your analysis as JSON:
{
  "reconciliation": {
    "total_rsf_rent_roll": 165432,
    "total_rsf_leases": 164890,
    "total_rsf_boma": 163500,
    "variance_rent_roll_vs_boma": 1932,
    "variance_percentage": 1.18,
    "estimated_annual_revenue_impact": 45168
  },
  "by_tenant": [
    {
      "tenant_name": "...",
      "suite": "...",
      "rsf_rent_roll": 10000,
      "rsf_lease": 9850,
      "rsf_boma": 9720,
      "variance": 280,
      "variance_pct": 2.88,
      "annual_impact": 6720,
      "recommendation": "Remeasure suite, verify lease amendment"
    }
  ],
  "issues": [
    {
      "severity": "high",
      "description": "Suite 400 shows 2,500 SF in rent roll but only 2,180 SF in BOMA report",
      "impact": "Potential $7,680 annual rent shortfall",
      "recommendation": "Request certified remeasurement before closing"
    }
  ]
}"""


class RSFReconciliationAgent(BaseAgent):
    """Agent specialized in RSF reconciliation across multiple data sources."""
    
    def __init__(self):
        super().__init__(
            name="RSFReconciliationAgent",
            system_prompt=RSF_RECONCILIATION_PROMPT
        )
    
    async def reconcile(
        self,
        rent_roll_data: dict,
        lease_data: Optional[list[dict]] = None,
        boma_data: Optional[dict] = None,
        average_rent_psf: float = 24.0
    ) -> dict:
        """Reconcile RSF across all available sources."""
        sources = {
            "rent_roll": rent_roll_data,
            "average_rent_psf": average_rent_psf
        }
        
        if lease_data:
            sources["leases"] = lease_data
        if boma_data:
            sources["boma_measurement"] = boma_data
        
        content = f"RSF data from multiple sources:\n{sources}"
        return await self.analyze(content)
