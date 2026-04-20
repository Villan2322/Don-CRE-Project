from agents.base import BaseAgent
from typing import Optional


RENT_ROLL_PROMPT = """You are an expert commercial real estate rent roll analysis agent.
Your job is to parse and normalize rent roll data, identifying any inconsistencies or errors.

When analyzing a rent roll, extract the following for each tenant:
- tenant_name: Tenant name (normalize to legal name if possible)
- suite: Suite or unit number
- rsf: Rentable square feet
- monthly_rent: Monthly base rent amount
- annual_rent: Annual base rent
- rent_psf: Rent per square foot
- lease_start: Lease start date (YYYY-MM-DD)
- lease_end: Lease end date (YYYY-MM-DD)
- status: Current, Expired, MTM (month-to-month), etc.

Also calculate and provide:
- Total occupied RSF
- Total vacant RSF
- Occupancy rate
- Total annual base rent
- Weighted average rent PSF
- WALT (Weighted Average Lease Term) in years

Identify any issues:
- Arithmetic errors (rent calculations don't match)
- Missing data
- Duplicate entries
- Inconsistent formatting
- Expired leases still shown as current

Return your analysis as a JSON object:
{
  "tenants": [
    {
      "tenant_name": "...",
      "suite": "...",
      "rsf": 10000,
      ...
    }
  ],
  "summary": {
    "total_occupied_rsf": 150000,
    "total_vacant_rsf": 10000,
    "occupancy_rate": 0.94,
    "total_annual_rent": 3500000,
    "weighted_avg_rent_psf": 23.33,
    "walt_years": 4.2
  },
  "issues": [
    {
      "type": "arithmetic_error",
      "description": "...",
      "affected_tenant": "...",
      "severity": "high"
    }
  ]
}"""


class RentRollAgent(BaseAgent):
    """Agent specialized in parsing and analyzing rent roll data."""
    
    def __init__(self):
        super().__init__(
            name="RentRollAgent",
            system_prompt=RENT_ROLL_PROMPT
        )
    
    async def parse_rent_roll(self, rent_roll_text: str, file_type: str = "excel") -> dict:
        """Parse and analyze rent roll data."""
        context = {"source_format": file_type}
        return await self.analyze(rent_roll_text, context)
    
    async def validate_against_leases(
        self, 
        rent_roll_data: dict, 
        lease_abstracts: list[dict]
    ) -> dict:
        """Validate rent roll data against lease abstracts."""
        validation_prompt = """Compare the rent roll data against the lease abstracts.
Identify any discrepancies in:
- RSF (square footage)
- Rent amounts
- Lease dates
- Tenant names

For each discrepancy, note:
- Field with discrepancy
- Rent roll value
- Lease value
- Recommended resolution"""
        
        content = f"Rent Roll Data:\n{rent_roll_data}\n\nLease Abstracts:\n{lease_abstracts}"
        return await self.analyze(content, {"validation_mode": True})
