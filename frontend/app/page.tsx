'use client'

import { useState, useCallback } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'
import { mockDealAnalysis } from '@/lib/mock-data'
import { TabId, DealAnalysis, RedFlag, Tenant, LeaseAbstract, UploadedDocument } from '@/lib/types'

// API response type from the backend (matches actual backend output)
interface AnalysisAPIResponse {
  success: boolean
  deal_name?: string
  analyzed_at?: string
  
  // Top-level fields from backend
  documents_processed?: number
  property_appraiser_sf?: number
  score?: number
  tier?: string
  rsf_recovery_sf?: number
  rsf_recovery_annual_value?: number
  
  // Nested structures
  rsf_analysis?: {
    reconciliation: {
      property_appraiser_sf?: number
      rent_roll_rsf?: number
      rent_roll_total_sf?: number
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
    sub_scores?: Record<string, number>
    red_flags?: Array<Record<string, unknown>>
    red_flag_count?: {
      critical: number
      high: number
      moderate: number
      low: number
    }
  }
  tenants?: Array<{
    name?: string
    tenant?: string
    suite?: string
    rsf?: number
    sf?: number
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
    id?: string
    category?: string
    severity?: string
    title?: string
    description?: string
    message?: string  // Backend uses 'message' field
    issue?: string
    financial_impact?: number
    recommended_action?: string
    recommendation?: string  // Backend uses 'recommendation' field
    action?: string
  }>
  what_to_get_next?: Array<string | { document?: string; why_needed?: string; priority?: number }>
  financial?: {
    noi?: number
    vacancy?: number
    walt?: number
  }
  documents?: {
    total: number
    files: Array<{ filename: string; type: string; confidence?: number }>
  }
  trace_log?: Array<{ stage: string; message: string; level: string }>
  error?: string
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('snapshot')
  const [analysisData, setAnalysisData] = useState<DealAnalysis | null>(null)
  const [hasRealData, setHasRealData] = useState(false)

  // Called when analysis completes - transform API response to DealAnalysis format
  const handleAnalysisComplete = useCallback((result: AnalysisAPIResponse) => {
    if (!result.success) {
      return
    }

    // Use top-level fields from backend (not nested under risk/rsf_analysis)
    const scoreValue = result.score ?? result.risk?.score ?? 0
    const tierValue = result.tier ?? result.risk?.tier ?? 'YELLOW'
    const rsfRecoverySf = result.rsf_recovery_sf ?? result.rsf_analysis?.recovery_opportunity?.sf ?? 0
    const rsfRecoveryValue = result.rsf_recovery_annual_value ?? result.rsf_analysis?.recovery_opportunity?.annual_value ?? 0
    const propertyAppraiserSf = result.property_appraiser_sf ?? result.rsf_analysis?.reconciliation?.property_appraiser_sf ?? 0

    // Transform API response to match DealAnalysis type from lib/types.ts
    // Backend uses 'message', frontend expects 'description'
    const redFlags: RedFlag[] = (result.red_flags || []).map((flag, i) => ({
      id: flag.id || `flag-${i}`,
      category: flag.category || 'General',
      severity: (flag.severity?.toUpperCase() === 'CRITICAL' ? 'HIGH' : flag.severity?.toUpperCase() || 'LOW') as 'HIGH' | 'MEDIUM' | 'LOW',
      description: flag.description || flag.message || flag.issue || 'No description provided',
      impact: flag.financial_impact ? `$${flag.financial_impact.toLocaleString()} potential impact` : 'Review document for details',
      resolution: flag.recommended_action || flag.recommendation || flag.action || 'Gather additional documentation',
    }))

    const tenants: Tenant[] = (result.tenants || []).map((t, i) => ({
      id: `tenant-${i}`,
      name: t.name || t.tenant || 'Unknown Tenant',
      suite: t.suite || '',
      rsf: t.rsf || t.sf || 0,
      bomaRsf: undefined,
      rsfDelta: undefined,
      monthlyRent: t.monthly_rent || (t.annual_rent ? t.annual_rent / 12 : 0),
      annualRent: t.annual_rent || 0,
      rentPSF: (t.rsf || t.sf) && t.annual_rent ? t.annual_rent / (t.rsf || t.sf || 1) : 0,
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

    // Normalize whatToGetNext to string array
    const whatToGetNext: string[] = (result.what_to_get_next || []).map(item => {
      if (typeof item === 'string') return item
      return item.document || 'Unknown document'
    })

    const transformed: DealAnalysis = {
      id: crypto.randomUUID(),
      dealName: result.deal_name || 'Analysis Results',
      propertyAddress: propertyAppraiserSf ? `PA Baseline: ${propertyAppraiserSf.toLocaleString()} SF` : 'Uploaded Documents',
      submittedAt: result.analyzed_at || new Date().toISOString(),
      score: scoreValue,
      tier: (tierValue.toUpperCase() || 'YELLOW') as 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED',
      subScores: {
        dataCompleteness: result.risk?.sub_scores?.data_completeness ?? 70,
        rsfAlignment: rsfRecoverySf > 0 ? 50 : 90,
        financialIntegrity: result.risk?.sub_scores?.financial_integrity ?? scoreValue,
        leaseLeverage: result.risk?.sub_scores?.lease_leverage ?? scoreValue,
        riskProfile: result.risk?.sub_scores?.risk_profile ?? scoreValue,
        documentCoverage: Math.min(100, (result.documents_processed || result.documents?.total || 0) * 20),
      },
      rsfReconciliation: {
        bomaTotalSF: propertyAppraiserSf || result.rsf_analysis?.reconciliation?.boma_rsf || 0,
        rentRollOccupiedSF: result.rsf_analysis?.reconciliation?.rent_roll_rsf || result.rsf_analysis?.reconciliation?.rent_roll_total_sf || 0,
        deltaSF: rsfRecoverySf || result.rsf_analysis?.reconciliation?.discrepancy_sf || 0,
        deltaPercent: result.rsf_analysis?.reconciliation?.discrepancy_pct || 0,
        estimatedAnnualRecovery: rsfRecoveryValue,
        alertTriggered: rsfRecoverySf > 0 || (result.rsf_analysis?.discrepancy_found ?? false),
      },
      financialSummary: {
        totalAnnualRent: tenants.reduce((sum, t) => sum + t.annualRent, 0),
        noi: result.financial?.noi ?? 0,
        capRate: 0,
        averageRentPSF: 0,
        vacancy: result.financial?.vacancy ?? 0,
        arDelinquency: 0,
      },
      walt: result.financial?.walt ?? 0,
      redFlags,
      whatToGetNext,
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
            hasRealData={hasRealData}
            onAnalysisComplete={handleAnalysisComplete}
          />
        </main>
      </div>
    </div>
  )
}
