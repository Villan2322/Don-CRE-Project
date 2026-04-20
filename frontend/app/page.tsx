'use client'

import { useState, useCallback } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'
import { mockDealAnalysis } from '@/lib/mock-data'
import { TabId, DealAnalysis, RedFlag, Tenant, LeaseAbstract, UploadedDocument } from '@/lib/types'

// API response type from the backend
interface AnalysisAPIResponse {
  success: boolean
  deal_name?: string
  rsf_analysis?: {
    reconciliation: {
      rent_roll_rsf?: number
      lease_rsf?: number
      boma_rsf?: number
      discrepancy_sf?: number
      discrepancy_pct?: number
    }
    recovery_opportunity?: {
      sf?: number
      annual_value?: number
    }
    discrepancy_found: boolean
  }
  risk?: {
    score: number
    tier: string
    red_flag_count: {
      critical: number
      high: number
      moderate: number
      low: number
    }
  }
  tenants?: Array<{
    name: string
    suite?: string
    rsf?: number
    annual_rent?: number
    monthly_rent?: number
    lease_start?: string
    lease_end?: string
    months_remaining?: number
    risk_level?: string
  }>
  lease_abstracts?: Array<{
    tenant_name?: string
    suite?: string
    rentable_sf?: number
    lease_commencement?: string
    lease_expiration?: string
    annual_base_rent?: number
    escalation?: string
    expense_structure?: string
    missing_fields?: string[]
  }>
  red_flags?: Array<{
    id: string
    category: string
    severity: string
    title: string
    description: string
    financial_impact?: number
    recommended_action?: string
  }>
  what_to_get_next?: string[]
  noi?: number
  walt_months?: number
  vacancy_pct?: number
  documents?: {
    total: number
    files: Array<{ filename: string; type: string }>
  }
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('snapshot')
  const [analysisData, setAnalysisData] = useState<DealAnalysis | null>(null)
  const [hasRealData, setHasRealData] = useState(false)

  // Called when analysis completes - transform API response to DealAnalysis format
  const handleAnalysisComplete = useCallback((result: AnalysisAPIResponse) => {
    if (!result.success) return

    // Transform API response to match DealAnalysis type from lib/types.ts
    const redFlags: RedFlag[] = (result.red_flags || []).map((flag, i) => ({
      id: flag.id || `flag-${i}`,
      category: flag.category,
      severity: (flag.severity?.toUpperCase() === 'CRITICAL' ? 'HIGH' : flag.severity?.toUpperCase() || 'LOW') as 'HIGH' | 'MEDIUM' | 'LOW',
      description: flag.description,
      impact: flag.financial_impact ? `$${flag.financial_impact.toLocaleString()} potential impact` : 'Unknown impact',
      resolution: flag.recommended_action,
    }))

    const tenants: Tenant[] = (result.tenants || []).map((t, i) => ({
      id: `tenant-${i}`,
      name: t.name,
      suite: t.suite || '',
      rsf: t.rsf || 0,
      bomaRsf: undefined,
      rsfDelta: undefined,
      monthlyRent: t.monthly_rent || (t.annual_rent ? t.annual_rent / 12 : 0),
      annualRent: t.annual_rent || 0,
      rentPSF: t.rsf && t.annual_rent ? t.annual_rent / t.rsf : 0,
      leaseStart: t.lease_start || '',
      leaseExpiry: t.lease_end || null,
      monthsRemaining: t.months_remaining ?? null,
      incomeConcentration: 0,
      riskLevel: (t.risk_level?.toUpperCase() || 'LOW') as 'LOW' | 'MEDIUM' | 'HIGH',
      arStatus: 'CURRENT' as const,
      arBalance: 0,
    }))

    const leaseAbstracts: LeaseAbstract[] = (result.lease_abstracts || []).map((la, i) => ({
      id: `abstract-${i}`,
      tenantName: la.tenant_name || 'Unknown',
      suite: la.suite || '',
      rsf: la.rentable_sf || 0,
      commencementDate: la.lease_commencement || '',
      expirationDate: la.lease_expiration || null,
      baseRent: la.annual_base_rent || 0,
      escalation: la.escalation || 'Unknown',
      expenseStructure: (la.expense_structure?.toUpperCase() || 'NNN') as 'NNN' | 'GROSS' | 'MODIFIED_GROSS',
      camCap: null,
      renewalOptions: null,
      tiAllowance: null,
      remeasurementRights: false,
      missingFields: la.missing_fields || [],
    }))

    const documents: UploadedDocument[] = (result.documents?.files || []).map((d, i) => ({
      id: `doc-${i}`,
      filename: d.filename,
      type: (d.type?.toUpperCase() || 'LEASE') as UploadedDocument['type'],
      uploadedAt: new Date().toISOString(),
      pageCount: 1,
      status: 'PROCESSED' as const,
    }))

    const transformed: DealAnalysis = {
      id: crypto.randomUUID(),
      dealName: result.deal_name || 'Analysis Results',
      propertyAddress: 'Uploaded Documents',
      submittedAt: new Date().toISOString(),
      score: result.risk?.score || 0,
      tier: (result.risk?.tier?.toUpperCase() || 'YELLOW') as 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED',
      subScores: {
        dataCompleteness: 70,
        rsfAlignment: result.rsf_analysis?.discrepancy_found ? 50 : 90,
        financialIntegrity: result.risk?.score || 0,
        leaseLeverage: result.risk?.score || 0,
        riskProfile: result.risk?.score || 0,
        documentCoverage: Math.min(100, (result.documents?.total || 0) * 20),
      },
      rsfReconciliation: {
        bomaTotalSF: result.rsf_analysis?.reconciliation.boma_rsf || 0,
        rentRollOccupiedSF: result.rsf_analysis?.reconciliation.rent_roll_rsf || 0,
        deltaSF: result.rsf_analysis?.reconciliation.discrepancy_sf || 0,
        deltaPercent: result.rsf_analysis?.reconciliation.discrepancy_pct || 0,
        estimatedAnnualRecovery: result.rsf_analysis?.recovery_opportunity?.annual_value || 0,
        alertTriggered: result.rsf_analysis?.discrepancy_found || false,
      },
      financialSummary: {
        totalAnnualRent: tenants.reduce((sum, t) => sum + t.annualRent, 0),
        noi: result.noi || 0,
        capRate: 0,
        averageRentPSF: 0,
        vacancy: result.vacancy_pct || 0,
        arDelinquency: 0,
      },
      walt: result.walt_months || 0,
      redFlags,
      whatToGetNext: result.what_to_get_next || [],
      tenants,
      leaseAbstracts,
      documents,
    }

    setAnalysisData(transformed)
    setHasRealData(true)
    // Auto-switch to snapshot tab to show results
    setActiveTab('snapshot')
  }, [])

  // Use real data if available, otherwise mock
  const displayData = hasRealData && analysisData ? analysisData : mockDealAnalysis

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header 
        dealName={hasRealData ? displayData.dealName : undefined}
        hasRealData={hasRealData}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar 
          activeTab={activeTab} 
          onTabChange={setActiveTab}
          hasRealData={hasRealData}
        />
        <main className="flex-1 overflow-y-auto p-6">
          <TabContent 
            activeTab={activeTab} 
            deal={displayData}
            onAnalysisComplete={handleAnalysisComplete}
          />
        </main>
      </div>
    </div>
  )
}
