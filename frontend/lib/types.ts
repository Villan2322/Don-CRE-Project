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
  redFlags: RedFlag[]
  whatToGetNext: (string | { document?: string; why_needed?: string; score_impact?: string | number; priority?: string | number })[]
  tenants: Tenant[]
  leaseAbstracts: LeaseAbstract[]
  documents: UploadedDocument[]
}

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
  rsf: number
  bomaRsf?: number
  rsfDelta?: number
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
  rsf: number
  commencementDate: string
  expirationDate: string | null
  baseRent: number
  escalation: string
  expenseStructure: 'NNN' | 'GROSS' | 'MODIFIED_GROSS'
  camCap: number | null
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

export type TabId = 'snapshot' | 'audit' | 'rent-roll' | 'lease-audit' | 'risk' | 'abstracts' | 'upload'
