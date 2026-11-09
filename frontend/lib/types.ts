// Mirrors the payload built by backend/services/deal_metrics.py::build_report.

export type Tier = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'
export type DealReadiness =
  | 'Proceed with confidence'
  | 'Proceed with conditions'
  | 'Material gaps'
  | 'Insufficient data'
export type Severity = 'HIGH' | 'MEDIUM' | 'LOW'

export interface ScoreReason {
  text: string
  earned: boolean
  points: number
}

export interface ScoreCategory {
  points: number
  max: number
  reasons: ScoreReason[]
}

export type ScoreCategoryKey =
  | 'dataCompleteness'
  | 'rsfAlignment'
  | 'financialIntegrity'
  | 'leaseLeverage'
  | 'riskProfile'
  | 'documentCoverage'

export interface RsfReconciliation {
  bomaTotalSF: number
  rentRollOccupiedSF: number
  occupiedSource: string | null
  deltaSF: number
  deltaPercent: number
  estimatedAnnualRecovery: number
  baseRentRecovery?: number
  camRecovery?: number
  camRatePSF?: number | null
  averageRentPSF?: number | null
  alertTriggered: boolean
  comparable: boolean
  countyTotalSF: number | null
  countyNote: string | null
}

export type LeverageCall = 'STRONG' | 'NEGOTIABLE' | 'NONE' | 'NO_LEASE' | 'OVERBILLED' | 'MATCHES'

export interface LeaseAuditRow {
  tenantId: string
  name: string
  suite: string
  billedRsf: number | null
  billedRsfSource: string | null
  bomaRsf: number | null
  bomaUsf: number | null
  deltaSF: number | null
  deltaPct: number | null
  billedLoadFactor: number | null
  bomaLoadFactor: number | null
  billedShare: number | null
  billedShareSource: string | null
  bomaShare: number | null
  rentPSF: number | null
  baseRentGap: number | null
  billedCam: number | null
  billedCamBasis: string | null
  correctCam: number | null
  camGap: number | null
  totalGap: number | null
  correctedAnnualRent: number | null
  recoversExpenses: boolean | null
  expenseNote: string | null
  leverage: { call: LeverageCall | null; reason: string; clause: string | null }
  terms: Record<string, string | number | null>
  leaseFile: string | null
}

export interface LeaseAudit {
  available: boolean
  tenants: LeaseAuditRow[]
  summary: {
    suitesMeasured: number
    suitesUnderbilled: number
    suitesOverbilled: number
    underbilledSF: number
    overbilledSF: number
    baseRentUpside: number | null
    camUpside: number | null
    totalUpside: number | null
    collectibleUpside: number | null
    pendingUpside?: number | null
    overbilledExposure: number | null
    expensePool: number | null
    expensePoolBasis: string | null
    camRatePSF: number | null
    bomaLoadFactor: number | null
    billedLoadFactor: number | null
    leverage: Partial<Record<LeverageCall, number>>
  }
}

export interface FinancialSummary {
  totalAnnualRent: number
  averageRentPSF: number
  noi: number | null
  noiBasis: string | null
  capRate: number | null
  capRateBasis: string | null
  vacancy: number | null
  arDelinquency: number
  camRecoveryRatio: number | null
}

export interface RedFlag {
  id: string
  severity: Severity
  category: string
  description: string
  impact: string
  resolution?: string | null
  source: 'computed' | 'ai_review'
  sourceDocuments?: string[]
}

export interface Tenant {
  id: string
  name: string
  suite: string
  rsf: number
  rentRollRsf: number | null
  leaseRsf: number | null
  bomaRsf: number | null
  rsfDelta: number | null
  monthlyRent: number
  annualRent: number
  rentPSF: number
  leaseStart: string | null
  leaseExpiry: string | null
  monthsRemaining: number | null
  monthToMonth: boolean
  incomeConcentration: number
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
  arStatus: 'CURRENT' | 'DELINQUENT' | 'AT_RISK'
  arBalance: number
  arOver60: number
  arNote: string | null
  hasLease: boolean
  sources: string[]
}

export interface LeaseAbstract {
  id: string
  tenantName: string
  suite: string
  rsf: number
  commencementDate: string | null
  expirationDate: string | null
  baseRent: number
  escalation: string
  expenseStructure: 'NNN' | 'GROSS' | 'MODIFIED_GROSS' | null
  expenseStructureText: string | null
  camCap: string | null
  renewalOptions: string | null
  tiAllowance: number | null
  remeasurementRights: boolean
  missingFields: string[]
  confidence: number | null
  sourceFile: string
}

export type DocumentType =
  | 'LEASE'
  | 'LEASE_ABSTRACT'
  | 'RENT_ROLL'
  | 'BOMA'
  | 'MANAGEMENT_REPORT'
  | 'COUNTY_PA'
  | 'FINANCIAL_MODEL'
  | 'CAM_RECONCILIATION'
  | 'OTHER'

export interface UploadedDocument {
  id: string
  filename: string
  type: DocumentType
  classificationConfidence: number | null
  uploadedAt: string
  pageCount: number
  ocr: boolean
  status: 'PROCESSED' | 'FAILED' | 'SKIPPED'
  note: string | null
}

export interface ArithmeticCheck {
  label: string
  status: 'pass' | 'warning' | 'fail'
  stated: number | null
  computed: number | null
  deltaPct: number | null
  formula: string
  detail: string | null
  source: string
}

export interface ExpiryBucket {
  label: string
  annualRent: number
  tenants: string[]
}

export interface DealAnalysis {
  id: string
  dealName: string
  propertyAddress: string
  submittedAt: string
  asOf: string
  dataAsOf: string | null
  dataAgeMonths: number | null
  landlordUseSpaces: { suite: string | null; name: string | null; rsf: number | null }[]
  score: number
  tier: Tier
  dealReadiness: DealReadiness
  subScores: Record<ScoreCategoryKey, number>
  scoreBreakdown: Record<ScoreCategoryKey, ScoreCategory>
  executiveSummary: string | null
  rsfReconciliation: RsfReconciliation
  leaseAudit?: LeaseAudit
  financialSummary: FinancialSummary
  walt: number | null
  waltCoverage: number
  buildingRsf: number | null
  vacantRsf: number
  redFlags: RedFlag[]
  whatToGetNext: string[]
  tenants: Tenant[]
  leaseAbstracts: LeaseAbstract[]
  documents: UploadedDocument[]
  arithmeticChecks: ArithmeticCheck[]
  expirySchedule: ExpiryBucket[]
  pipelineErrors: string[]
  isSample: boolean
}

export type TabId = 'snapshot' | 'lease-audit' | 'audit' | 'rent-roll' | 'expirations' | 'risk' | 'abstracts' | 'upload'
