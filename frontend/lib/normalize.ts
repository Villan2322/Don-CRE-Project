/**
 * Adapts the backend AnalysisResult shape to the frontend DealAnalysis shape.
 * This is the single source-of-truth for the mapping between the two schemas.
 */

import type { AnalysisResult } from './api'
import type {
  DealAnalysis,
  RedFlag,
  Tenant,
  LeaseAbstract,
  UploadedDocument,
} from './types'

function scoreToTier(score: number): DealAnalysis['tier'] {
  if (score >= 90) return 'GREEN'
  if (score >= 75) return 'YELLOW'
  if (score >= 60) return 'ORANGE'
  return 'RED'
}

function severityMap(s: string): RedFlag['severity'] {
  const upper = s.toUpperCase()
  if (upper === 'CRITICAL' || upper === 'HIGH') return 'HIGH'
  if (upper === 'MEDIUM') return 'MEDIUM'
  return 'LOW'
}

function docTypeMap(t: string): UploadedDocument['type'] {
  const map: Record<string, UploadedDocument['type']> = {
    lease: 'LEASE',
    rent_roll: 'RENT_ROLL',
    boma_measurement: 'BOMA',
    operating_statement: 'FINANCIAL_MODEL',
    ar_aging: 'RENT_ROLL_XLSX',
    cam_reconciliation: 'CAM_RECONCILIATION',
    estoppel: 'LEASE_ABSTRACT',
  }
  return map[t.toLowerCase()] ?? 'LEASE'
}

function docStatusMap(s: string): UploadedDocument['status'] {
  if (s === 'completed') return 'PROCESSED'
  if (s === 'failed') return 'FAILED'
  return 'PROCESSING'
}

export function normalizeAnalysisResult(result: AnalysisResult): DealAnalysis {
  const score = result.deal_score.overall_score
  const summary = result.financial_summary ?? {}

  // Sub-scores: backend uses snake_case keys, frontend camelCase
  const sub = result.deal_score.sub_scores ?? {}
  const subScores: DealAnalysis['subScores'] = {
    dataCompleteness: sub['document_completeness'] ?? sub['dataCompleteness'] ?? 75,
    rsfAlignment: sub['rsf_integrity'] ?? sub['rsfAlignment'] ?? 75,
    financialIntegrity: sub['income_verification'] ?? sub['financialIntegrity'] ?? 75,
    leaseLeverage: sub['lease_quality'] ?? sub['leaseLeverage'] ?? 75,
    riskProfile: sub['red_flag_impact'] ?? sub['riskProfile'] ?? 75,
    documentCoverage: sub['expense_analysis'] ?? sub['documentCoverage'] ?? 75,
  }

  const rsf = result.rsf_reconciliation
  const variancePct = Math.abs(rsf.variance_percentage ?? 0)

  const rsfReconciliation: DealAnalysis['rsfReconciliation'] = {
    bomaTotalSF: rsf.total_rsf_boma ?? 0,
    rentRollOccupiedSF: rsf.total_rsf_rent_roll ?? 0,
    deltaSF: rsf.variance_rent_roll_vs_boma ?? 0,
    deltaPercent: variancePct,
    estimatedAnnualRecovery: rsf.estimated_annual_revenue_impact ?? 0,
    alertTriggered: variancePct >= 2,
  }

  // Tenants
  const tenants: Tenant[] = ((result.tenants ?? []) as any[]).map((t, i) => {
    const msRemaining =
      t.days_to_expiry != null ? Math.round(t.days_to_expiry / 30) : null
    const arBalance =
      (t.ar_current ?? 0) +
      (t.ar_30_days ?? 0) +
      (t.ar_60_days ?? 0) +
      (t.ar_90_plus ?? 0)
    const arStatus: Tenant['arStatus'] =
      (t.ar_90_plus ?? 0) > 0
        ? 'DELINQUENT'
        : (t.ar_60_days ?? 0) > 0
        ? 'AT_RISK'
        : 'CURRENT'

    const totalRent = (result.financial_summary as any)?.total_annual_rent ?? 1
    const concentration =
      totalRent > 0 ? (t.annual_rent ?? 0) / totalRent : 0

    const riskStr = (t.risk_level ?? 'low').toUpperCase()
    const riskLevel: Tenant['riskLevel'] =
      riskStr === 'HIGH' ? 'HIGH' : riskStr === 'MEDIUM' ? 'MEDIUM' : 'LOW'

    return {
      id: t.tenant_id ?? `tenant-${i}`,
      name: t.tenant_name ?? 'Unknown',
      suite: t.suite ?? '',
      rsf: t.rsf_rent_roll ?? 0,
      bomaRsf: t.rsf_boma ?? undefined,
      rsfDelta: t.rsf_variance ?? undefined,
      monthlyRent: t.monthly_rent ?? 0,
      annualRent: t.annual_rent ?? 0,
      rentPSF: t.rent_psf ?? 0,
      leaseStart: t.lease_start ?? '',
      leaseExpiry: t.lease_end ?? null,
      monthsRemaining: msRemaining,
      incomeConcentration: concentration,
      riskLevel,
      arStatus,
      arBalance,
    }
  })

  // Lease abstracts
  const leaseAbstracts: LeaseAbstract[] = ((result.lease_abstracts ?? []) as any[]).map(
    (la, i) => {
      const expStructure = (la.expense_structure ?? '').toUpperCase()
      const expenseStructure: LeaseAbstract['expenseStructure'] =
        expStructure.includes('NNN')
          ? 'NNN'
          : expStructure.includes('GROSS') && expStructure.includes('MODIFIED')
          ? 'MODIFIED_GROSS'
          : expStructure.includes('GROSS')
          ? 'GROSS'
          : 'NNN'

      return {
        id: la.lease_id ?? `la-${i}`,
        tenantName: la.tenant_name ?? 'Unknown',
        suite: la.suite ?? '',
        rsf: la.rsf ?? 0,
        commencementDate: la.lease_start ?? '',
        expirationDate: la.lease_end ?? null,
        baseRent: la.annual_base_rent ?? 0,
        escalation: la.rent_escalation ?? 'None specified',
        expenseStructure,
        camCap: null,
        renewalOptions: la.renewal_options ?? null,
        tiAllowance: la.tenant_improvements ?? null,
        remeasurementRights: false,
        missingFields: la.missing_fields ?? [],
      }
    }
  )

  // Red flags
  const redFlags: RedFlag[] = ((result.red_flags ?? []) as any[]).map((rf, i) => ({
    id: rf.id ?? `rf-${i}`,
    severity: severityMap(rf.severity ?? 'medium'),
    category: rf.category ?? 'general',
    description: rf.description ?? '',
    impact: rf.financial_impact != null ? `$${Number(rf.financial_impact).toLocaleString()} estimated impact` : rf.title ?? '',
    resolution: rf.recommended_action ?? undefined,
  }))

  // Documents
  const documents: UploadedDocument[] = ((result.documents_processed ?? []) as any[]).map(
    (d, i) => ({
      id: d.id ?? `doc-${i}`,
      filename: d.filename ?? 'document',
      type: docTypeMap(d.document_type ?? 'other'),
      uploadedAt: d.uploaded_at ?? new Date().toISOString(),
      pageCount: d.page_count ?? 0,
      status: docStatusMap(d.status ?? 'completed'),
    })
  )

  // WALT: calculate from tenants if not in summary
  const waltMonths =
    tenants.length > 0
      ? Math.round(
          tenants.reduce((sum, t) => sum + (t.monthsRemaining ?? 0), 0) /
            tenants.length
        )
      : 0

  const totalAnnualRent =
    (summary as any)?.total_annual_rent ??
    tenants.reduce((s, t) => s + t.annualRent, 0)

  return {
    id: result.deal_id,
    dealName: result.property_name ?? 'Property Under Analysis',
    propertyAddress: result.property_address ?? 'Address TBD',
    submittedAt: result.analysis_date ?? new Date().toISOString(),
    score,
    tier: scoreToTier(score),
    subScores,
    rsfReconciliation,
    financialSummary: {
      totalAnnualRent,
      noi: (summary as any)?.noi ?? totalAnnualRent * 0.65,
      capRate: (summary as any)?.cap_rate ?? 0,
      averageRentPSF:
        (summary as any)?.weighted_avg_rent_psf ??
        (summary as any)?.averageRentPSF ??
        0,
      vacancy:
        1 -
        ((summary as any)?.occupancy_rate ??
          (summary as any)?.vacancy != null
          ? 1 - (summary as any)?.vacancy
          : 0.95),
      arDelinquency: 0,
    },
    walt: waltMonths,
    redFlags,
    whatToGetNext: result.what_to_get_next ?? [],
    tenants,
    leaseAbstracts,
    documents,
  }
}
