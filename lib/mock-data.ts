import { DealAnalysis } from './types'

// Empty initial state - no mock data
// Real data will be populated after document analysis via the Python backend
export const emptyDealAnalysis: DealAnalysis = {
  id: '',
  dealName: '',
  propertyAddress: '',
  submittedAt: '',
  score: 0,
  tier: 'RED',
  dealReadiness: 'Insufficient data',
  subScores: {
    dataCompleteness: 0,
    rsfAlignment: 0,
    financialIntegrity: 0,
    leaseLeverage: 0,
    riskProfile: 0,
    documentCoverage: 0,
  },
  rsfReconciliation: {
    bomaTotalSF: 0,
    rentRollOccupiedSF: 0,
    deltaSF: 0,
    deltaPercent: 0,
    estimatedAnnualRecovery: 0,
    alertTriggered: false,
  },
  financialSummary: {
    totalAnnualRent: 0,
    noi: 0,
    capRate: 0,
    averageRentPSF: 0,
    vacancy: 0,
    arDelinquency: 0,
  },
  walt: 0,
  redFlags: [],
  whatToGetNext: [],
  tenants: [],
  leaseAbstracts: [],
  documents: [],
}

// Historical score data - empty until real analysis
export const scoreHistory: { date: string; score: number; documents: number }[] = []

// Income concentration - empty until real analysis
export const incomeConcentration: { name: string; value: number; fill: string }[] = []

// WALT timeline - empty until real analysis
export const waltTimeline: { month: string; atRisk: number; secure: number }[] = []
