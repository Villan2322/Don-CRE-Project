from agents.base import BaseAgent


DOCUMENT_CLASSIFIER_PROMPT = """You are an expert commercial real estate document classification agent.
Your job is to identify document types and assess document completeness.

Document Types to Identify:
- LEASE: Commercial lease agreement, amendment, or extension
- RENT_ROLL: Tenant roster with rent details
- BOMA_MEASUREMENT: Building/suite measurement report (BOMA standard)
- OPERATING_STATEMENT: Income/expense statement, P&L
- AR_AGING: Accounts receivable aging report
- CAM_RECONCILIATION: Common area maintenance reconciliation
- ESTOPPEL: Tenant estoppel certificate
- OFFERING_MEMO: Property offering memorandum
- SURVEY: Property survey or site plan
- TITLE: Title report or commitment
- ENVIRONMENTAL: Phase I/II environmental report
- APPRAISAL: Property appraisal
- OTHER: Other document type

For each document, determine:
1. Document type
2. Document date (if visible)
3. Key entities mentioned (property, tenants)
4. Page count
5. Quality/legibility assessment

Return your classification as JSON:
{
  "classification": {
    "document_type": "LEASE",
    "confidence": 0.95,
    "document_date": "2023-06-15",
    "property_name": "Gateway Office Plaza",
    "tenants_mentioned": ["TechCorp Inc."],
    "page_count": 45,
    "quality": "good",
    "notes": "Fully executed lease with all exhibits"
  }
}"""


COMPLETENESS_PROMPT = """You are an expert commercial real estate due diligence document completeness analyst.
Given the list of documents received, identify what is missing for a complete due diligence package.

Required Documents (Priority):
1. CRITICAL (must have):
   - Current rent roll
   - All executed leases and amendments
   - BOMA measurement report
   - Last 2 years operating statements

2. HIGH PRIORITY:
   - AR aging report (current)
   - CAM reconciliation (last 2 years)
   - Property survey
   - Title commitment

3. RECOMMENDED:
   - Tenant estoppels
   - Service contracts
   - Insurance certificates
   - Environmental reports
   - Building permits/certificates of occupancy

Return your analysis as JSON:
{
  "completeness_score": 72,
  "documents_received": ["rent_roll", "lease_1", "lease_2"],
  "missing_documents": [
    {
      "type": "BOMA_MEASUREMENT",
      "priority": "critical",
      "reason": "Required to verify RSF for rent calculations"
    }
  ],
  "what_to_request_next": [
    "BOMA measurement report for all occupied suites",
    "Operating statements for 2022 and 2023",
    "AR aging report as of current month"
  ]
}"""


class DocumentClassifierAgent(BaseAgent):
    """Agent for document classification and completeness assessment."""
    
    def __init__(self):
        super().__init__(
            name="DocumentClassifierAgent",
            system_prompt=DOCUMENT_CLASSIFIER_PROMPT
        )
    
    async def classify_document(self, document_text: str, filename: str) -> dict:
        """Classify a single document."""
        context = {"filename": filename}
        return await self.analyze(document_text[:5000], context)  # First 5000 chars for classification
    
    async def assess_completeness(self, documents_received: list[dict]) -> dict:
        """Assess completeness of document package."""
        # Switch to completeness prompt
        self.system_prompt = COMPLETENESS_PROMPT
        
        content = f"Documents received:\n{documents_received}"
        result = await self.analyze(content)
        
        # Reset to classification prompt
        self.system_prompt = DOCUMENT_CLASSIFIER_PROMPT
        
        return result
