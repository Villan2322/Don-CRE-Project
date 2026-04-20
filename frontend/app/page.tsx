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
    expiry?: string        // from lease_expiry_schedule
    months_remaining_val?: number
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
    flag?: string  // Backend uses 'flag' as the identifier/description
    description?: string
    message?: string
    issue?: string
    impact?: string  // Backend returns 'impact' directly
    financial_impact?: number
    resolution?: string  // Backend returns 'resolution' directly
    recommended_action?: string
    recommendation?: string
    action?: string
  }>
  what_to_get_next?: Array<string | { document?: string; why_needed?: string; priority?: number }>
  lease_abstracts?: Array<{
    id?: string
    tenant_name?: string
    tenant?: string
    suite?: string
    rentable_sf?: number
    rsf?: number
    lease_commencement?: string
    commencement?: string
    lease_expiration?: string | null
    expiration?: string | null
    annual_base_rent?: number
    base_rent_annual?: number
    escalation?: string
    escalations?: string
    expense_structure?: string
    missing_fields?: string[]
  }>
  financial?: {
    noi?: number
    vacancy?: number
    walt?: number
    total_annual_rent?: number
    average_rent_psf?: number
  }
  documents?: {
    total: number
    files: Array<{ filename: string; type: string; confidence?: number }>
  }
  trace_log?: Array<{ stage: string; message: string; level: string; timestamp?: string }>
  cove?: {
    threshold_pct: number
    verified_tenants: number
    unverified_tenants: number
    total_tenants: number
    suppressed_fields: string[]
  }
  error?: string
}

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('snapshot')
  const [analysisData, setAnalysisData] = useState<DealAnalysis | null>(null)
  const [hasRealData, setHasRealData] = useState(false)

  // Called when analysis completes - transform API response to DealAnalysis format
  const handleAnalysisComplete = useCallback((result: AnalysisAPIResponse) => {
    // Backend returns the report dict directly - success may be undefined or missing
    // Only bail if there is an explicit error with no usable data
    const hasError = result.error && !result.score && !result.tenants?.length
    if (hasError) {
      return
    }

    // Use top-level fields from backend (not nested under risk/rsf_analysis)
    const scoreValue = result.score ?? result.risk?.score ?? 0
    const tierValue = result.tier ?? result.risk?.tier ?? 'YELLOW'
    const rsfRecoverySf = result.rsf_recovery_sf ?? result.rsf_analysis?.recovery_opportunity?.sf ?? 0
    const rsfRecoveryValue = result.rsf_recovery_annual_value ?? result.rsf_analysis?.recovery_opportunity?.annual_value ?? 0
    const propertyAppraiserSf = result.property_appraiser_sf ?? result.rsf_analysis?.reconciliation?.property_appraiser_sf ?? 0

    // Transform API response to match DealAnalysis type from lib/types.ts
    // Backend uses: flag (identifier), impact (string), resolution (string), severity
    const normalizeSeverity = (s: string | undefined): 'HIGH' | 'MEDIUM' | 'LOW' => {
      const val = (s || '').toUpperCase().trim()
      if (['HIGH', 'CRITICAL'].includes(val)) return 'HIGH'
      if (['MEDIUM', 'MODERATE', 'WARNING'].includes(val)) return 'MEDIUM'
      return 'LOW'
    }

    const redFlags: RedFlag[] = (result.red_flags || [])
      .filter((rf): rf is NonNullable<typeof rf> => rf != null)
      .map((rf, i) => ({
        id: rf.id || `flag-${i}`,
        category: rf.category || rf.flag?.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()) || 'General',
        severity: normalizeSeverity(rf.severity),
        description: rf.description || rf.message || rf.issue || rf.flag?.replace(/_/g, ' ') || 'No description provided',
        impact: rf.impact || (rf.financial_impact ? `$${Number(rf.financial_impact).toLocaleString()} potential impact` : 'Review document for details'),
        resolution: rf.resolution || rf.recommended_action || rf.recommendation || rf.action || 'Gather additional documentation',
      }))

    const tenants: Tenant[] = (result.tenants || [])
      .filter((t): t is NonNullable<typeof t> => t != null)  // Filter null items
      .map((t, i) => {
        // Backend synthesis returns many field name variations - handle all of them
        const tenantName = t.name || t.tenant || t.tenant_name || t.tenantName || 'Unknown Tenant'
        const sf = Number(t.rsf || t.sf || t.rentable_sf || t.rent_roll_rsf || 0)
        const annualRent = Number(t.annual_rent || t.annualRent || t.base_rent_annual || 0)
        const monthlyRent = Number(t.monthly_rent || t.monthlyRent || (annualRent ? annualRent / 12 : 0))
        const leaseEnd = t.lease_end || t.expiry || t.lease_expiration || t.expiration || null
        const monthsLeft = t.months_remaining != null ? Number(t.months_remaining) : null

        return {
          id: `tenant-${i}`,
          name: String(tenantName),
          suite: String(t.suite || t.unit || ''),
          rsf: sf,
          bomaRsf: undefined,
          rsfDelta: undefined,
          monthlyRent,
          annualRent,
          rentPSF: sf > 0 && annualRent > 0 ? annualRent / sf : 0,
          leaseStart: String(t.lease_start || t.commencement || t.lease_commencement || ''),
          leaseExpiry: leaseEnd,
          monthsRemaining: monthsLeft,
          incomeConcentration: 0,
          riskLevel: (['LOW','MEDIUM','HIGH'].includes(String(t.risk_level || '').toUpperCase())
            ? String(t.risk_level).toUpperCase()
            : 'LOW') as 'LOW' | 'MEDIUM' | 'HIGH',
          arStatus: 'CURRENT' as const,
          arBalance: 0,
          // COVE confidence fields from backend
          confidencePct: t._confidence_pct ?? undefined,
          coveStatus: (t._cove_status === 'VERIFIED' || t._cove_status === 'UNVERIFIED')
            ? t._cove_status as 'VERIFIED' | 'UNVERIFIED'
            : undefined,
          passesSeenCount: t._passes_seen ?? undefined,
        }
      })

    const leaseAbstracts: LeaseAbstract[] = (result.lease_abstracts || [])
      .filter((la): la is NonNullable<typeof la> => la != null)
      .map((la, i) => ({
        id: `abstract-${i}`,
        tenantName: String(la.tenant_name || la.tenant || 'Unknown'),
        suite: String(la.suite || ''),
        rsf: Number(la.rentable_sf || la.rsf || 0),
        commencementDate: String(la.lease_commencement || la.commencement || ''),
        expirationDate: la.lease_expiration || la.expiration || null,
        baseRent: Number(la.annual_base_rent || la.base_rent_annual || 0),
        escalation: String(la.escalation || 'Unknown'),
        expenseStructure: (la.expense_structure?.toUpperCase() || 'NNN') as 'NNN' | 'GROSS' | 'MODIFIED_GROSS',
        camCap: null,
        renewalOptions: null,
        tiAllowance: null,
        remeasurementRights: false,
        missingFields: Array.isArray(la.missing_fields) ? la.missing_fields : [],
      }))

    const documents: UploadedDocument[] = (result.documents?.files || []).map((d, i) => ({
      id: `doc-${i}`,
      filename: d.filename,
      type: (d.type?.toUpperCase() || 'LEASE') as UploadedDocument['type'],
      uploadedAt: new Date().toISOString(),
      pageCount: 1,
      status: 'PROCESSED' as const,
    }))

    // Normalize whatToGetNext to string array - filter nulls and handle all shapes
    const whatToGetNext: string[] = (result.what_to_get_next || [])
      .filter((item): item is NonNullable<typeof item> => item != null)
      .map(item => {
        if (typeof item === 'string') return item
        if (typeof item === 'object') {
          return item.document || item.why_needed || JSON.stringify(item)
        }
        return String(item)
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
        rsfAlignment: result.risk?.sub_scores?.rsf_accuracy ?? (rsfRecoverySf > 0 ? 50 : 90),
        financialIntegrity: result.risk?.sub_scores?.financial_integrity ?? scoreValue,
        leaseLeverage: result.risk?.sub_scores?.lease_health ?? result.risk?.sub_scores?.lease_leverage ?? scoreValue,
        riskProfile: result.risk?.sub_scores?.risk_profile ?? scoreValue,
        documentCoverage: Math.min(100, (result.documents_processed || result.documents?.total || 0) * 20),
      },
      rsfReconciliation: {
        bomaTotalSF: propertyAppraiserSf || result.rsf_analysis?.reconciliation?.boma_rsf || 0,
        rentRollOccupiedSF: result.rsf_analysis?.reconciliation?.rent_roll_total_sf || result.rsf_analysis?.reconciliation?.rent_roll_rsf || 0,
        deltaSF: rsfRecoverySf || result.rsf_analysis?.reconciliation?.discrepancy_sf || 0,
        deltaPercent: result.rsf_analysis?.reconciliation?.discrepancy_pct || 0,
        estimatedAnnualRecovery: rsfRecoveryValue,
        alertTriggered: rsfRecoverySf > 0 || (result.rsf_analysis?.discrepancy_found ?? false),
      },
      financialSummary: {
        totalAnnualRent: result.financial?.total_annual_rent ?? tenants.reduce((sum, t) => sum + t.annualRent, 0),
        noi: result.financial?.noi ?? 0,
        capRate: 0,
        averageRentPSF: result.financial?.average_rent_psf ?? 0,
        vacancy: result.financial?.vacancy ?? 0,
        arDelinquency: 0,
      },
      walt: result.financial?.walt ?? 0,
      redFlags,
      whatToGetNext,
      tenants,
      leaseAbstracts,
      documents,
      traceLog: (result.trace_log || []).map(l => ({
        stage: l.stage,
        message: l.message,
        level: l.level,
        timestamp: l.timestamp || new Date().toISOString(),
      })),
      cove: result.cove ?? undefined,
    }

    setAnalysisData(transformed)
    setHasRealData(true)
    // Auto-switch to upload tab so user sees the trace immediately
    setActiveTab('upload')
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
