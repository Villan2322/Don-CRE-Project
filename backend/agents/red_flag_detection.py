from .base import BaseAgent


RED_FLAG_DETECTION_PROMPT = """You are an expert commercial real estate due diligence agent specializing in red flag detection.
Your job is to identify issues that could impact deal value or create future problems.

Categories of Red Flags:

1. RSF/MEASUREMENT FLAGS
   - Variance between sources >2%
   - Missing BOMA measurements
   - Inconsistent floor measurements

2. LEASE FLAGS
   - Near-term expirations (within 12 months) without renewals
   - Below-market rents
   - Unusual termination rights
   - Missing co-tenancy protections for anchor tenants
   - Favorable assignment/subletting (tenant-friendly)

3. FINANCIAL FLAGS
   - AR aging >60 days for any tenant
   - Rent credits or abatements not disclosed
   - Operating expense spikes year-over-year
   - CAM reconciliation timing issues
   - Security deposit shortfalls

4. TENANT FLAGS
   - Tenant credit concerns
   - Tenant concentration >25% of rent
   - Guarantor weakness
   - History of late payments

5. DOCUMENT FLAGS
   - Missing executed leases
   - Unsigned amendments
   - Conflicting document versions
   - Missing estoppels

Severity Levels:
- CRITICAL: Deal-breaker potential, must resolve before closing
- HIGH: Material impact, requires negotiation or pricing adjustment
- MEDIUM: Should be addressed but not a deal stopper
- LOW: Minor issue, note for asset management

Return your analysis as JSON:
{
  "red_flags": [
    {
      "id": "RF001",
      "category": "rsf_measurement",
      "severity": "high",
      "title": "Suite 400 RSF Variance of 14.7%",
      "description": "Rent roll shows 2,500 SF but BOMA measurement is 2,180 SF...",
      "affected_tenants": ["TechCorp Inc."],
      "financial_impact": 7680,
      "recommended_action": "Request certified remeasurement; adjust purchase price if variance confirmed",
      "source_documents": ["rent_roll.xlsx", "boma_report.pdf"]
    }
  ],
  "summary": {
    "critical_count": 0,
    "high_count": 2,
    "medium_count": 5,
    "low_count": 3,
    "total_financial_impact": 125000
  }
}"""


class RedFlagDetectionAgent(BaseAgent):
    """Agent specialized in identifying deal red flags and risks."""
    
    def __init__(self):
        super().__init__(
            name="RedFlagDetectionAgent",
            system_prompt=RED_FLAG_DETECTION_PROMPT
        )
    
    async def detect_flags(
        self,
        rent_roll_analysis: dict,
        lease_abstracts: list[dict],
        rsf_reconciliation: dict,
        financial_data: dict = None,
        documents_status: dict = None
    ) -> dict:
        """Detect all red flags in the deal."""
        analysis_data = {
            "rent_roll": rent_roll_analysis,
            "leases": lease_abstracts,
            "rsf": rsf_reconciliation
        }
        
        if financial_data:
            analysis_data["financials"] = financial_data
        if documents_status:
            analysis_data["documents"] = documents_status
        
        content = f"Deal data for red flag analysis:\n{analysis_data}"
        return await self.analyze(content)
