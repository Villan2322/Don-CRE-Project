import { DealAnalysis, Tenant, LeaseAbstract, RedFlag, UploadedDocument } from '@/lib/types'

// Transform the raw Python backend response into the frontend DealAnalysis type.
export function transformBackendResponse(data: any, dealName: string): DealAnalysis {
  const now = new Date().toISOString()
  const dealId = data.deal_id || `deal-${Date.now()}`

  // Extract tenants from rent_roll_analysis or extractions
  const rentRollData = data.rent_roll_analysis || {}
  const tenantRows = rentRollData.tenants || rentRollData.rows || []

  const tenants: Tenant[] = tenantRows.map((t: any, i: number) => ({
    id: t.tenant_id || `t-${i + 1}`,
    name: t.tenant_name || t.name || `Tenant ${i + 1}`,
    suite: t.suite || t.unit || '',
    rsf: parseFloat(t.rsf || t.sf || t.square_feet || 0),
    bomaRsf: parseFloat(t.boma_rsf || t.rsf_boma || t.rsf || 0),
    rsfDelta: parseFloat(t.rsf_variance || 0),
    monthlyRent: parseFloat(t.monthly_rent || t.base_rent || 0),
    annualRent: parseFloat(t.annual_rent || (t.monthly_rent || 0) * 12),
    rentPSF: parseFloat(t.rent_psf || t.base_rent_psf || 0),
    leaseStart: t.lease_start || t.commencement_date || '',
    leaseExpiry: t.lease_end || t.expiration_date || '',
    monthsRemaining: t.months_remaining || (t.days_to_expiry ? Math.ceil(t.days_to_expiry / 30) : 12),
    incomeConcentration: parseFloat(t.income_concentration || t.percent_of_total || 0),
    riskLevel: mapRiskLevel(t.risk_level),
    arStatus: t.ar_90_plus > 0 ? 'DELINQUENT' : 'CURRENT',
    arBalance:
      parseFloat(t.ar_current || 0) +
      parseFloat(t.ar_30_days || 0) +
      parseFloat(t.ar_60_days || 0) +
      parseFloat(t.ar_90_plus || 0),
  }))

  // Extract lease abstracts
  const extractedLeases = data.extractions?.filter((e: any) => (e.doc_type || e.document_type) === 'LEASE') || []
  const leaseAbstracts: LeaseAbstract[] = extractedLeases.map((l: any, i: number) => {
    const ex = l.extraction || l
    return {
      id: l.doc_id || l.lease_id || `la-${i + 1}`,
      tenantName: ex.tenant_name || '',
      suite: ex.suite || '',
      rsf: parseFloat(ex.rsf || 0),
      commencementDate: ex.lease_start || ex.commencement_date || '',
      expirationDate: ex.lease_end || ex.expiration_date || '',
      baseRent: parseFloat(ex.annual_base_rent || ex.annual_rent || 0),
      escalation: ex.rent_escalation || '',
      expenseStructure: mapExpenseStructure(ex.expense_structure),
      camCap: ex.cam_cap || null,
      renewalOptions: ex.renewal_options || '',
      tiAllowance: parseFloat(ex.tenant_improvements || 0),
      remeasurementRights: !!ex.remeasurement_rights,
      missingFields: l.missing_fields || ex.missing_fields || [],
    }
  })

  // Extract red flags
  const redFlagsData = data.red_flags_result?.red_flags || data.red_flags || []
  const redFlags: RedFlag[] = redFlagsData.map((rf: any, i: number) => ({
    id: rf.id || `rf-${i + 1}`,
    severity: mapSeverity(rf.severity),
    category: rf.category || rf.title || 'Issue',
    description: rf.description || rf.title || '',
    impact: rf.financial_impact ? `$${Number(rf.financial_impact).toLocaleString()} impact` : undefined,
    resolution: rf.recommended_action || '',
  }))

  // RSF Reconciliation
  const rsfData = data.rsf_reconciliation || data.rsf_recovery || {}
  const rsfReconciliation = {
    bomaTotalSF: parseFloat(rsfData.total_rsf_boma || rsfData.boma_sf || 0),
    rentRollOccupiedSF: parseFloat(rsfData.total_rsf_rent_roll || rsfData.rent_roll_sf || 0),
    deltaSF: parseFloat(rsfData.variance_rent_roll_vs_boma || rsfData.delta_sf || 0),
    deltaPercent: parseFloat(rsfData.variance_percentage || 0),
    estimatedAnnualRecovery: parseFloat(rsfData.estimated_annual_revenue_impact || rsfData.annual_recovery || 0),
    alertTriggered: (rsfData.variance_percentage || 0) > 5,
  }

  // Financial summary
  const financialData = data.synthesis || data.financial_summary || {}
  const totalAnnualRent =
    tenants.reduce((sum, t) => sum + t.annualRent, 0) || parseFloat(financialData.total_annual_rent || 0)
  const totalRsf = tenants.reduce((sum, t) => sum + t.rsf, 0)

  // Score
  const scoreData = data.score_summary || data.deal_score_result || {}
  const score = scoreData.overall || scoreData.overall_score || 50
  const tier = mapTier(score, scoreData.deal_readiness)

  // What to get next
  const completenessData = data.completeness_result || {}
  const whatToGetNext = completenessData.missing_documents ||
    completenessData.recommendations || [
      'Additional lease documents',
      'BOMA measurement report',
      'AR aging report',
    ]

  // Documents processed
  const processedDocs: UploadedDocument[] = (data.classified_documents || []).map((d: any) => ({
    id: d.doc_id || d.id || d.document_id || crypto.randomUUID(),
    filename: d.filename || d.name,
    type: mapDocType(d.doc_type || d.document_type || d.classification),
    uploadedAt: now,
    pageCount: d.page_count || 1,
    status: 'PROCESSED' as const,
  }))

  return {
    id: dealId,
    dealName: data.deal_name || dealName,
    propertyAddress: data.property_address || `${dealName}, FL`,
    submittedAt: now,
    score,
    tier,
    dealReadiness: mapDealReadiness(score, scoreData.deal_readiness),
    subScores: scoreData.sub_scores || {
      dataCompleteness: 12,
      rsfAlignment: 10,
      financialIntegrity: 12,
      leaseLeverage: 10,
      riskProfile: 10,
      documentCoverage: 12,
    },
    rsfReconciliation,
    financialSummary: {
      totalAnnualRent,
      noi: parseFloat(financialData.noi || totalAnnualRent * 0.72),
      capRate: parseFloat(financialData.cap_rate || 7.5),
      averageRentPSF: totalRsf > 0 ? totalAnnualRent / totalRsf : 0,
      vacancy: parseFloat(financialData.vacancy || 5),
      arDelinquency: tenants.reduce((sum, t) => sum + t.arBalance, 0),
    },
    walt:
      scoreData.walt ||
      Math.round(tenants.reduce((sum, t) => sum + (t.monthsRemaining || 0), 0) / Math.max(tenants.length, 1)),
    redFlags,
    whatToGetNext,
    tenants,
    leaseAbstracts,
    documents: processedDocs,
  }
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
    if (readiness.includes('confidence')) return 'GREEN'
    if (readiness.includes('conditions')) return 'YELLOW'
    if (readiness.includes('gaps')) return 'ORANGE'
    if (readiness.includes('Insufficient')) return 'RED'
  }
  if (score >= 80) return 'GREEN'
  if (score >= 60) return 'YELLOW'
  if (score >= 40) return 'ORANGE'
  return 'RED'
}

function mapDealReadiness(score: number, readiness?: string): DealAnalysis['dealReadiness'] {
  if (readiness) {
    if (readiness.includes('confidence')) return 'Proceed with confidence'
    if (readiness.includes('conditions')) return 'Proceed with conditions'
    if (readiness.includes('gaps')) return 'Material gaps'
    return 'Insufficient data'
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
