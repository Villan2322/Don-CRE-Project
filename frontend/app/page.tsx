'use client'

import { useState, useCallback } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'
import { mockDealAnalysis } from '@/lib/mock-data'
import { TabId, DealAnalysis } from '@/lib/types'

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('upload')
  const [analysisData, setAnalysisData] = useState<DealAnalysis | null>(null)
  const [hasRealData, setHasRealData] = useState(false)

  // Called when analysis completes - transform API response to DealAnalysis format
  const handleAnalysisComplete = useCallback((result: {
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
      lease_end?: string
      months_remaining?: number
      risk_level?: string
    }>
    lease_abstracts?: Array<{
      tenant_name?: string
      suite?: string
      rentable_sf?: number
      lease_expiration?: string
      annual_base_rent?: number
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
  }) => {
    if (!result.success) return

    // Transform API response to match DealAnalysis type
    const transformed: DealAnalysis = {
      id: crypto.randomUUID(),
      name: result.deal_name || 'Analysis Results',
      propertyAddress: 'Uploaded Documents',
      overallScore: result.risk?.score || 0,
      tier: (result.risk?.tier || 'UNKNOWN') as 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED',
      subScores: {
        documentCompleteness: 70,
        financialHealth: result.risk?.score || 0,
        leaseQuality: result.risk?.score || 0,
        rsfReconciliation: result.rsf_analysis?.discrepancy_found ? 50 : 90,
        tenantCreditworthiness: 75,
      },
      redFlags: (result.red_flags || []).map((flag, i) => ({
        id: flag.id || `flag-${i}`,
        category: flag.category as 'RSF_DISCREPANCY' | 'LEASE_RISK' | 'FINANCIAL_ISSUE' | 'DATA_QUALITY' | 'DOCUMENT_MISSING',
        severity: flag.severity as 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW',
        title: flag.title,
        description: flag.description,
        financialImpact: flag.financial_impact,
        recommendedAction: flag.recommended_action || 'Review and address',
      })),
      rsfReconciliation: {
        rentRollTotalSF: result.rsf_analysis?.reconciliation.rent_roll_rsf || 0,
        rentRollOccupiedSF: result.rsf_analysis?.reconciliation.rent_roll_rsf || 0,
        leaseTotalSF: result.rsf_analysis?.reconciliation.lease_rsf || 0,
        bomaTotalSF: result.rsf_analysis?.reconciliation.boma_rsf,
        discrepancySF: result.rsf_analysis?.reconciliation.discrepancy_sf || 0,
        discrepancyPercent: result.rsf_analysis?.reconciliation.discrepancy_pct || 0,
        alertTriggered: result.rsf_analysis?.discrepancy_found || false,
        estimatedAnnualRecovery: result.rsf_analysis?.recovery_opportunity?.annual_value || 0,
      },
      financialSummary: {
        noi: result.noi || 0,
        totalAnnualRent: (result.tenants || []).reduce((sum, t) => sum + (t.annual_rent || 0), 0),
        averageRentPSF: 0,
        vacancyPercent: result.vacancy_pct || 0,
        arOutstanding: 0,
      },
      walt: result.walt_months || 0,
      tenants: (result.tenants || []).map((t, i) => ({
        id: `tenant-${i}`,
        name: t.name,
        suite: t.suite || '',
        rentRollSF: t.rsf || 0,
        leaseSF: t.rsf,
        bomaSF: undefined,
        annualRent: t.annual_rent || 0,
        rentPSF: t.rsf ? (t.annual_rent || 0) / t.rsf : 0,
        leaseStart: undefined,
        leaseExpiry: t.lease_end,
        monthsRemaining: t.months_remaining,
        riskLevel: (t.risk_level || 'LOW') as 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL',
        issues: [],
      })),
      leaseAbstracts: (result.lease_abstracts || []).map((la, i) => ({
        id: `abstract-${i}`,
        tenantName: la.tenant_name || 'Unknown',
        suite: la.suite,
        rentableSF: la.rentable_sf,
        leaseCommencement: undefined,
        leaseExpiration: la.lease_expiration,
        baseRent: la.annual_base_rent,
        rentEscalation: undefined,
        camStructure: undefined,
        options: undefined,
        missingFields: la.missing_fields || [],
      })),
      whatToGetNext: result.what_to_get_next || [],
      documents: (result.documents?.files || []).map((d, i) => ({
        id: `doc-${i}`,
        name: d.filename,
        type: d.type as 'LEASE' | 'RENT_ROLL' | 'BOMA' | 'CAM_RECONCILIATION' | 'MANAGEMENT_REPORT' | 'OTHER',
        status: 'PROCESSED' as const,
        uploadedAt: new Date().toISOString(),
      })),
      lastUpdated: new Date().toISOString(),
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
        dealName={hasRealData ? displayData.name : undefined}
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
