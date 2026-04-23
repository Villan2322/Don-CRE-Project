export interface DealAnalysis {
  id: string
  dealName: string
  propertyAddress: string
  submittedAt: string
  score: number
  tier: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'
  subScores: {
    dataCompleteness: number
    rsfAlignment: number
    financialIntegrity: number
    leaseLeverage: number
    riskProfile: number
    documentCoverage: number
  }
  rsfReconciliation: {
    bomaTotalSF: number
    rentRollOccupiedSF: number
    deltaSF: number
    deltaPercent: number
    estimatedAnnualRecovery: number
    alertTriggered: boolean
  }
  financialSummary: {
    totalAnnualRent: number
    noi: number
    capRate: number
    averageRentPSF: number
    vacancy: number
    arDelinquency: number
  }
  walt: number
  camReconciliation: CAMReconciliation
  redFlags: RedFlag[]
  whatToGetNext: string[]
  tenants: Tenant[]
  leaseAbstracts: LeaseAbstract[]
  documents: UploadedDocument[]
}

// ── CAM Reconciliation ────────────────────────────────────────────────────────

export interface CAMReconciliation {
  totalRecoverableExpenses: number
  buildingTotalRSF: number
  tenantCAMSummary: TenantCAMRecord[]
  totalBilled: number
  totalOwed: number
  overUnderCollection: number
  expenseCategories: ExpenseCategory[]
}

export interface TenantCAMRecord {
  tenantId: string
  tenantName: string
  suite: string
  usf: number
  rsf: number
  // Load factor = RSF / USF
  loadFactor: number
  // Load factor as stated in the executed lease
  leaseLoadFactor: number | null
  // Delta between implied and lease-stated load factor
  loadFactorDelta: number | null
  proRataShare: number
  totalRecoverableExpenses: number
  camOwed: number
  camBilled: number
  // Positive = over-collected, negative = under-collected
  overUnder: number
  camCap: number | null
  camCapApplied: boolean
  grossUpApplied: boolean
  expenseExclusions: string[]
  mgmtFeeCapPct: number | null
  baseYear: number | null
  // True = flat monthly CAM, no annual true-up
  fixedCAM: boolean
  controllableCap: number | null
  anchorExclusion: boolean
}

export interface ExpenseCategory {
  glCode: string
  description: string
  totalAmount: number
  recoverable: boolean
  exclusionReason: string | null
}

// ── Core types ────────────────────────────────────────────────────────────────

export interface RedFlag {
  id: string
  severity: 'HIGH' | 'MEDIUM' | 'LOW'
  category: string
  description: string
  impact: string
  resolution?: string
}

export interface Tenant {
  id: string
  name: string
  suite: string
  // Usable square footage (from floor plan)
  usf: number
  rsf: number
  bomaRsf?: number
  rsfDelta?: number
  // Implied load factor = RSF / USF
  loadFactor: number
  // Load factor as stated in the executed lease
  leaseLoadFactor: number | null
  proRataShare: number
  monthlyRent: number
  annualRent: number
  rentPSF: number
  leaseStart: string
  leaseExpiry: string | null
  monthsRemaining: number | null
  incomeConcentration: number
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
  arStatus: 'CURRENT' | 'DELINQUENT' | 'AT_RISK'
  arBalance: number
}

export interface LeaseAbstract {
  id: string
  tenantName: string
  suite: string
  usf: number
  rsf: number
  // Load factor stated in the executed lease
  loadFactor: number | null
  commencementDate: string
  expirationDate: string | null
  baseRent: number
  escalation: string
  expenseStructure: 'NNN' | 'GROSS' | 'MODIFIED_GROSS'
  // Annual CAM increase cap (e.g. 5 = 5%)
  camCap: number | null
  // Gross-up clause: expenses are grossed up when occupancy < threshold
  camGrossUp: boolean
  grossUpThreshold: number | null
  // GL categories explicitly excluded from expense recovery
  expenseExclusions: string[]
  // Max recoverable management fee as a percentage
  mgmtFeeCap: number | null
  // Base year stop: tenant pays only increases above this year
  baseYear: number | null
  // True = flat monthly CAM with no annual true-up
  fixedCAM: boolean
  // Cap on controllable expenses only (taxes/insurance excluded)
  controllableCamCap: number | null
  // Anchor tenant SF excluded from denominator in this lease
  anchorExclusion: boolean
  renewalOptions: string | null
  tiAllowance: number | null
  remeasurementRights: boolean
  missingFields: string[]
}

export interface UploadedDocument {
  id: string
  filename: string
  type: 'LEASE' | 'RENT_ROLL' | 'BOMA' | 'MANAGEMENT_REPORT' | 'COUNTY_PA' | 'FINANCIAL_MODEL' | 'LEASE_ABSTRACT' | 'RENT_ROLL_XLSX' | 'CAM_RECONCILIATION'
  uploadedAt: string
  pageCount: number
  status: 'PROCESSED' | 'PROCESSING' | 'FAILED'
}

export type TabId = 'snapshot' | 'audit' | 'rent-roll' | 'lease-audit' | 'cam' | 'risk' | 'abstracts' | 'upload'
