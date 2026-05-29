import { DealAnalysis, Tenant, LeaseAbstract, RedFlag, UploadedDocument } from '@/lib/types'

// Transform the raw Python backend response into the frontend DealAnalysis type.
//
// The backend returns the bulk of its analysis nested under `synthesis` plus
// per-document `extractions`. This transform reads from those real locations:
//   - extractions[].extraction.tenants / building_totals / vacancy_summary / collection_status
//   - synthesis.lease_audit (walt_months, lease_expiry_schedule)
//   - synthesis.rent_verification (total_annual_rent, tenant_shares)
//   - synthesis.financial_summary (noi, occupancy_pct, ar_concerns)
//   - synthesis.red_flags
//   - synthesis.what_to_get_next
//   - synthesis.rsf_reconciliation
//   - score_summary (overall_score, tier, sub_scores)
export function transformBackendResponse(data: any, dealName: string): DealAnalysis {
  const now = new Date().toISOString()
  const dealId = data.deal_id || `deal-${Date.now()}`
  const synthesis = data.synthesis || {}

  // --- Locate the rent roll extraction (per-tenant detail lives here) ---
  const extractions: any[] = Array.isArray(data.extractions) ? data.extractions : []
  const rentRollExtraction = extractions.find(
    (e) => (e.doc_type || e.document_type) === 'RENT_ROLL' || e?.extraction?.tenants
  )
  const ex = rentRollExtraction?.extraction || {}
  const rawTenants: any[] = ex.tenants || []
  const buildingTotals = ex.building_totals || {}
  const vacancySummary = ex.vacancy_summary || {}
  const collectionStatus = ex.collection_status || {}

  // --- Synthesis sub-objects ---
  const leaseAudit = synthesis.lease_audit || {}
  const expirySchedule: any[] = leaseAudit.lease_expiry_schedule || []
  const rentVerification = synthesis.rent_verification || {}
  const tenantShares: any[] = rentVerification.tenant_shares || []
  const financial = synthesis.financial_summary || {}

  // Lookup helpers (match by tenant name, case-insensitive)
  const norm = (s: string) => (s || '').trim().toLowerCase()
  const shareByName = new Map<string, number>(
    tenantShares.map((s) => [norm(s.tenant), Number(s.share_pct) || 0])
  )
  const expiryByName = new Map<string, any>(expirySchedule.map((e) => [norm(e.tenant), e]))

  const totalAnnualRentBase =
    Number(buildingTotals.total_annual_rent) ||
    Number(rentVerification.total_annual_rent) ||
    rawTenants.reduce((sum, t) => sum + (Number(t.annual_rent) || Number(t.monthly_rent) * 12 || 0), 0)

  // --- Tenants ---
  const tenants: Tenant[] = rawTenants.map((t: any, i: number) => {
    const name = t.tenant_name || t.name || `Tenant ${i + 1}`
    const annualRent = Number(t.annual_rent) || Number(t.monthly_rent) * 12 || 0
    const expiryInfo = expiryByName.get(norm(name))
    const sharePct =
      shareByName.get(norm(name)) ??
      (totalAnnualRentBase > 0 ? Math.round((annualRent / totalAnnualRentBase) * 1000) / 10 : 0)
    return {
      id: t.suite ? `t-${t.suite}` : `t-${i + 1}`,
      name,
      suite: t.suite || t.unit || '',
      rsf: Number(t.rsf) || 0,
      bomaRsf: Number(t.boma_rsf) || Number(t.rsf) || 0,
      rsfDelta: Number(t.rsf_variance) || 0,
      monthlyRent: Number(t.monthly_rent) || Math.round(annualRent / 12),
      annualRent,
      rentPSF: Number(t.psf_annual) || Number(t.rent_psf) || 0,
      leaseStart: t.lease_start || t.commencement_date || '',
      leaseExpiry: t.lease_end || t.expiration_date || expiryInfo?.expiry || null,
      monthsRemaining:
        expiryInfo?.months_remaining ??
        (t.lease_end ? monthsUntil(t.lease_end) : null),
      incomeConcentration: sharePct,
      riskLevel: mapRiskLevel(expiryInfo?.risk_level || t.risk_level),
      arStatus: 'CURRENT',
      arBalance: 0,
    }
  })

  // --- Lease abstracts (only present if LEASE docs were uploaded) ---
  const extractedLeases = extractions.filter(
    (e) => (e.doc_type || e.document_type) === 'LEASE'
  )
  const leaseAbstracts: LeaseAbstract[] = extractedLeases.map((l: any, i: number) => {
    const le = l.extraction || l
    return {
      id: l.doc_id || `la-${i + 1}`,
      tenantName: le.tenant_name || '',
      suite: le.suite || '',
      rsf: Number(le.rsf) || 0,
      commencementDate: le.lease_start || le.commencement_date || '',
      expirationDate: le.lease_end || le.expiration_date || null,
      baseRent: Number(le.annual_base_rent) || Number(le.annual_rent) || 0,
      escalation: le.rent_escalation || le.escalation || '',
      expenseStructure: mapExpenseStructure(le.expense_structure),
      camCap: le.cam_cap ?? null,
      renewalOptions: le.renewal_options || null,
      tiAllowance: Number(le.tenant_improvements) || null,
      remeasurementRights: !!le.remeasurement_rights,
      missingFields: le.missing_fields || [],
    }
  })

  // --- Red flags (synthesis.red_flags: { severity, flag, impact, resolution }) ---
  const rawRedFlags: any[] = synthesis.red_flags || data.red_flags_result?.red_flags || []
  const redFlags: RedFlag[] = rawRedFlags.map((rf: any, i: number) => ({
    id: rf.id || `rf-${i + 1}`,
    severity: mapSeverity(rf.severity),
    category: rf.category || categorize(rf.flag || rf.title || rf.description || ''),
    description: rf.flag || rf.description || rf.title || '',
    impact: rf.impact || rf.financial_impact || '',
    resolution: rf.resolution || rf.recommended_action || '',
  }))

  // --- RSF reconciliation ---
  const rsfData = synthesis.rsf_reconciliation || data.rsf_reconciliation || {}
  const deltaPercent = Number(rsfData.variance_percentage ?? rsfData.delta_percent) || 0
  const rsfReconciliation = {
    bomaTotalSF: Number(rsfData.total_rsf_boma ?? rsfData.boma_sf) || 0,
    rentRollOccupiedSF:
      Number(rsfData.total_rsf_rent_roll ?? rsfData.rent_roll_sf) ||
      Number(buildingTotals.occupied_rsf) ||
      0,
    deltaSF: Number(rsfData.variance_sf ?? rsfData.delta_sf) || 0,
    deltaPercent,
    estimatedAnnualRecovery:
      Number(rsfData.estimated_annual_revenue_impact ?? rsfData.annual_recovery) || 0,
    alertTriggered: Math.abs(deltaPercent) > 5,
  }

  // --- Financial summary ---
  const occupancyRate = Number(buildingTotals.occupancy_rate ?? financial.occupancy_pct)
  const vacancy = Number.isFinite(occupancyRate)
    ? Math.round((100 - occupancyRate) * 10) / 10
    : Number(vacancySummary.vacancy_rate) || 0
  const totalRsf = Number(buildingTotals.total_rsf) || tenants.reduce((s, t) => s + t.rsf, 0)
  const hasArData =
    collectionStatus.delinquent_tenants !== undefined ||
    collectionStatus.collection_rate !== undefined
  const arDelinquency = hasArData ? Number(collectionStatus.delinquent_tenants) > 0 ? null : 0 : null

  const financialSummary = {
    totalAnnualRent: totalAnnualRentBase,
    noi: financial.noi === null || financial.noi === undefined ? null : Number(financial.noi),
    capRate:
      financial.cap_rate === null || financial.cap_rate === undefined
        ? null
        : Number(financial.cap_rate),
    averageRentPSF:
      Number(buildingTotals.average_psf) ||
      (totalRsf > 0 ? Math.round((totalAnnualRentBase / totalRsf) * 100) / 100 : 0),
    vacancy,
    arDelinquency,
  }

  // --- WALT ---
  const walt = leaseAudit.walt_months
    ? Math.round(Number(leaseAudit.walt_months))
    : tenants.length > 0
      ? Math.round(
          tenants.reduce((s, t) => s + (t.monthsRemaining || 0), 0) / tenants.length
        )
      : 0

  // --- Score ---
  const scoreData = data.score_summary || synthesis.deal_score || {}
  const score = Number(scoreData.overall_score ?? scoreData.overall) || 0
  const ss = scoreData.sub_scores || {}
  const subScores = {
    dataCompleteness: Number(ss.document_completeness) || 0,
    rsfAlignment: Number(ss.data_consistency) || 0,
    financialIntegrity: Number(ss.financial_health) || 0,
    leaseLeverage: Number(ss.lease_quality) || 0,
    riskProfile: Number(ss.risk_factors) || 0,
    documentCoverage: Number(ss.document_completeness) || 0,
  }

  // --- What to get next (synthesis.what_to_get_next: { document, why_needed, priority }) ---
  const rawNext: any[] = synthesis.what_to_get_next || data.completeness_result?.missing_documents || []
  const whatToGetNext: string[] =
    rawNext.length > 0
      ? rawNext
          .slice()
          .sort((a, b) => (a.priority || 99) - (b.priority || 99))
          .map((n) => (typeof n === 'string' ? n : n.document || n.name || ''))
          .filter(Boolean)
      : ['Operating statement (T12)', 'Lease agreements', 'AR aging report']

  // --- Documents processed ---
  const classified: any[] = data.classified_documents || []
  const sourceDocs = classified.length > 0 ? classified : extractions
  const documents: UploadedDocument[] = sourceDocs.map((d: any, i: number) => ({
    id: d.doc_id || d.id || d.document_id || `doc-${i + 1}`,
    filename: d.filename || d.name || `Document ${i + 1}`,
    type: mapDocType(d.doc_type || d.document_type || d.classification),
    uploadedAt: now,
    pageCount: d.page_count || 1,
    status: 'PROCESSED' as const,
  }))

  return {
    id: dealId,
    dealName: data.deal_name || dealName,
    propertyAddress: data.property_address || dealName,
    submittedAt: now,
    score,
    tier: mapTier(score, scoreData.tier || scoreData.deal_readiness),
    dealReadiness: mapDealReadiness(score, scoreData.tier || scoreData.deal_readiness),
    subScores,
    rsfReconciliation,
    financialSummary,
    walt,
    redFlags,
    whatToGetNext,
    tenants,
    leaseAbstracts,
    documents,
  }
}

function monthsUntil(dateStr: string): number | null {
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return null
  const now = new Date()
  const months = (d.getFullYear() - now.getFullYear()) * 12 + (d.getMonth() - now.getMonth())
  return Math.max(0, months)
}

function categorize(text: string): string {
  const t = text.toLowerCase()
  if (t.includes('concentration')) return 'Concentration Risk'
  if (t.includes('rsf') || t.includes('measurement') || t.includes('sf')) return 'RSF Discrepancy'
  if (t.includes('ar ') || t.includes('delinqu') || t.includes('collection')) return 'AR Delinquency'
  if (t.includes('noi') || t.includes('operating') || t.includes('financial')) return 'Financial Data'
  if (t.includes('roll') || t.includes('expir') || t.includes('walt')) return 'Lease Rollover'
  if (t.includes('lease') || t.includes('missing')) return 'Missing Documents'
  return 'Issue'
}

function mapRiskLevel(level: string | undefined): 'LOW' | 'MEDIUM' | 'HIGH' {
  if (!level) return 'LOW'
  const l = level.toLowerCase()
  if (l === 'critical' || l === 'high') return 'HIGH'
  if (l === 'medium') return 'MEDIUM'
  return 'LOW'
}

function mapSeverity(severity: string | undefined): 'HIGH' | 'MEDIUM' | 'LOW' {
  if (!severity) return 'MEDIUM'
  const s = severity.toLowerCase()
  if (s === 'critical' || s === 'high') return 'HIGH'
  if (s === 'low') return 'LOW'
  return 'MEDIUM'
}

function mapExpenseStructure(structure: string | undefined): 'NNN' | 'MODIFIED_GROSS' | 'GROSS' {
  if (!structure) return 'NNN'
  const s = structure.toLowerCase()
  if (s.includes('gross') && s.includes('modif')) return 'MODIFIED_GROSS'
  if (s.includes('gross')) return 'GROSS'
  return 'NNN'
}

function mapTier(score: number, readiness?: string): 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED' {
  if (readiness) {
    const r = readiness.toLowerCase()
    if (r.includes('confidence') || r.includes('strong')) return 'GREEN'
    if (r.includes('conditions') || r.includes('review')) return 'YELLOW'
    if (r.includes('gaps') || r.includes('caution')) return 'ORANGE'
    if (r.includes('insufficient') || r.includes('reject')) return 'RED'
  }
  if (score >= 80) return 'GREEN'
  if (score >= 60) return 'YELLOW'
  if (score >= 40) return 'ORANGE'
  return 'RED'
}

function mapDealReadiness(score: number, readiness?: string): DealAnalysis['dealReadiness'] {
  if (readiness) {
    const r = readiness.toLowerCase()
    if (r.includes('confidence') || r.includes('strong')) return 'Proceed with confidence'
    if (r.includes('conditions') || r.includes('review')) return 'Proceed with conditions'
    if (r.includes('gaps') || r.includes('caution')) return 'Material gaps'
    if (r.includes('insufficient') || r.includes('reject')) return 'Insufficient data'
  }
  if (score >= 80) return 'Proceed with confidence'
  if (score >= 60) return 'Proceed with conditions'
  if (score >= 40) return 'Material gaps'
  return 'Insufficient data'
}

function mapDocType(type: string | undefined): UploadedDocument['type'] {
  if (!type) return 'MANAGEMENT_REPORT'
  const t = type.toLowerCase()
  if (t.includes('lease') && t.includes('abstract')) return 'LEASE_ABSTRACT'
  if (t.includes('lease')) return 'LEASE'
  if (t.includes('rent') && (t.includes('xlsx') || t.includes('excel'))) return 'RENT_ROLL_XLSX'
  if (t.includes('rent') || t.includes('roll')) return 'RENT_ROLL'
  if (t.includes('boma')) return 'BOMA'
  if (t.includes('cam')) return 'CAM_RECONCILIATION'
  if (t.includes('county') || t.includes('pa') || t.includes('appraiser')) return 'COUNTY_PA'
  if (t.includes('financial') || t.includes('model')) return 'FINANCIAL_MODEL'
  return 'MANAGEMENT_REPORT'
}
