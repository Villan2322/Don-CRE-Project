import { NextRequest, NextResponse } from 'next/server'
import { DealAnalysis, Tenant, LeaseAbstract, RedFlag, UploadedDocument } from '@/lib/types'

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { documents, dealName, files } = body

    if (!documents || !Array.isArray(documents) || documents.length === 0) {
      return NextResponse.json(
        { error: 'No documents provided for analysis' },
        { status: 400 }
      )
    }

    // In production (Vercel deployment), call the Python backend
    const isProduction = process.env.VERCEL_ENV === 'production' || process.env.VERCEL_ENV === 'preview'
    
    if (isProduction && files && files.length > 0) {
      try {
        const backendUrl = process.env.VERCEL_URL 
          ? `https://${process.env.VERCEL_URL}` 
          : ''
        
        console.log('[Backend] Starting analysis with', files.length, 'files')
        
        // Create FormData for the Python backend
        const formData = new FormData()
        formData.append('deal_name', dealName || 'Untitled Deal')
        
        // Attach files if provided as base64
        for (const file of files) {
          if (file.data) {
            const buffer = Buffer.from(file.data, 'base64')
            const blob = new Blob([buffer], { type: file.type || 'application/octet-stream' })
            formData.append('files', blob, file.filename)
          }
        }
        
        // Step 1: Call /backend/analyze to start the pipeline
        const analyzeResponse = await fetch(`${backendUrl}/backend/analyze`, {
          method: 'POST',
          body: formData,
        })
        
        if (!analyzeResponse.ok) {
          const errorText = await analyzeResponse.text()
          console.error('[Backend] Analyze failed:', analyzeResponse.status, errorText)
          throw new Error(`Backend analyze failed: ${errorText}`)
        }
        
        const analyzeResult = await analyzeResponse.json()
        console.log('[Backend] Analyze result keys:', Object.keys(analyzeResult))
        
        // The backend now returns full data directly (serverless can't persist state)
        // Transform the response directly instead of making a second call
        const analysis = transformBackendResponse(analyzeResult, dealName || analyzeResult.deal_name || 'Analyzed Deal')
        
        return NextResponse.json({
          success: true,
          analysis,
          backend: true,
        })
      } catch (backendError) {
        console.error('[Backend] Connection failed:', backendError)
        // Fall through to mock data
      }
    }

    // Fallback: Mock analysis for local development or if backend unavailable
    console.log('[Mock] Using mock analysis')
    await new Promise(resolve => setTimeout(resolve, 2000))

    const analysis = generateMockAnalysis(documents, dealName)

    return NextResponse.json({
      success: true,
      analysis,
      backend: false,
    })
  } catch (error) {
    console.error('Analysis error:', error)
    return NextResponse.json(
      { error: 'Failed to run analysis' },
      { status: 500 }
    )
  }
}

// Transform the raw backend response to frontend DealAnalysis type
function transformBackendResponse(data: any, dealName: string): DealAnalysis {
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
    monthsRemaining: t.months_remaining || t.days_to_expiry ? Math.ceil(t.days_to_expiry / 30) : 12,
    incomeConcentration: parseFloat(t.income_concentration || t.percent_of_total || 0),
    riskLevel: mapRiskLevel(t.risk_level),
    arStatus: t.ar_90_plus > 0 ? 'DELINQUENT' : 'CURRENT',
    arBalance: parseFloat(t.ar_current || 0) + parseFloat(t.ar_30_days || 0) + parseFloat(t.ar_60_days || 0) + parseFloat(t.ar_90_plus || 0),
  }))

  // Extract lease abstracts
  const extractedLeases = data.extractions?.filter((e: any) => e.document_type === 'lease') || []
  const leaseAbstracts: LeaseAbstract[] = extractedLeases.map((l: any, i: number) => ({
    id: l.lease_id || `la-${i + 1}`,
    tenantName: l.tenant_name || '',
    suite: l.suite || '',
    rsf: parseFloat(l.rsf || 0),
    commencementDate: l.lease_start || l.commencement_date || '',
    expirationDate: l.lease_end || l.expiration_date || '',
    baseRent: parseFloat(l.annual_base_rent || l.annual_rent || 0),
    escalation: l.rent_escalation || '',
    expenseStructure: mapExpenseStructure(l.expense_structure),
    camCap: l.cam_cap || null,
    renewalOptions: l.renewal_options || '',
    tiAllowance: parseFloat(l.tenant_improvements || 0),
    remeasurementRights: !!l.remeasurement_rights,
    missingFields: l.missing_fields || [],
  }))

  // Extract red flags
  const redFlagsData = data.red_flags_result?.red_flags || data.red_flags || []
  const redFlags: RedFlag[] = redFlagsData.map((rf: any, i: number) => ({
    id: rf.id || `rf-${i + 1}`,
    severity: mapSeverity(rf.severity),
    category: rf.category || rf.title || 'Issue',
    description: rf.description || rf.title || '',
    impact: rf.financial_impact ? `$${rf.financial_impact.toLocaleString()} impact` : undefined,
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
  const totalAnnualRent = tenants.reduce((sum, t) => sum + t.annualRent, 0) || parseFloat(financialData.total_annual_rent || 0)
  const totalRsf = tenants.reduce((sum, t) => sum + t.rsf, 0)

  // Score
  const scoreData = data.score_summary || data.deal_score_result || {}
  const score = scoreData.overall || scoreData.overall_score || 50
  const tier = mapTier(score, scoreData.deal_readiness)

  // What to get next
  const completenessData = data.completeness_result || {}
  const whatToGetNext = completenessData.missing_documents || completenessData.recommendations || [
    'Additional lease documents',
    'BOMA measurement report',
    'AR aging report',
  ]

  // Documents processed
  const processedDocs: UploadedDocument[] = (data.classified_documents || []).map((d: any) => ({
    id: d.id || d.document_id,
    filename: d.filename || d.name,
    type: mapDocType(d.document_type || d.classification),
    uploadedAt: now,
    pageCount: d.page_count || 1,
    status: 'PROCESSED' as const,
  }))

  const analysis: DealAnalysis = {
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
    walt: scoreData.walt || Math.round(tenants.reduce((sum, t) => sum + (t.monthsRemaining || 0), 0) / Math.max(tenants.length, 1)),
    redFlags,
    whatToGetNext,
    tenants,
    leaseAbstracts,
    documents: processedDocs,
  }

  return analysis
}

function transformPartialResult(result: any, dealName?: string): DealAnalysis {
  const now = new Date().toISOString()
  return {
    id: result.deal_id,
    dealName: dealName || 'Analyzed Deal',
    propertyAddress: '',
    submittedAt: now,
    score: result.overall_score || 50,
    tier: result.deal_readiness === 'Proceed with confidence' ? 'GREEN' :
          result.deal_readiness === 'Proceed with conditions' ? 'YELLOW' :
          result.deal_readiness === 'Material gaps' ? 'ORANGE' : 'RED',
    dealReadiness: result.deal_readiness || 'Proceed with conditions',
    subScores: { dataCompleteness: 10, rsfAlignment: 10, financialIntegrity: 10, leaseLeverage: 10, riskProfile: 10, documentCoverage: 10 },
    rsfReconciliation: { bomaTotalSF: 0, rentRollOccupiedSF: 0, deltaSF: 0, deltaPercent: 0, estimatedAnnualRecovery: 0, alertTriggered: false },
    financialSummary: { totalAnnualRent: 0, noi: 0, capRate: 0, averageRentPSF: 0, vacancy: 0, arDelinquency: 0 },
    walt: 0,
    redFlags: [],
    whatToGetNext: ['Analysis in progress - refresh for full results'],
    tenants: [],
    leaseAbstracts: [],
    documents: [],
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
  if (!type) return 'OTHER'
  const t = type.toLowerCase()
  if (t.includes('lease')) return 'LEASE'
  if (t.includes('rent') || t.includes('roll')) return 'RENT_ROLL'
  if (t.includes('boma')) return 'BOMA_MEASUREMENT'
  if (t.includes('operat')) return 'OPERATING_STATEMENT'
  if (t.includes('ar') || t.includes('aging')) return 'AR_AGING'
  if (t.includes('cam')) return 'CAM_RECONCILIATION'
  if (t.includes('estoppel')) return 'ESTOPPEL'
  return 'OTHER'
}

// Mock analysis generator for local development
function generateMockAnalysis(documents: any[], dealName?: string): DealAnalysis {
  const dealId = `deal-${Date.now()}`
  const now = new Date().toISOString()
  
  const firstDoc = documents[0]?.filename || 'Unknown Property'
  const propertyName = dealName || firstDoc
    .replace(/\.(pdf|xlsx|xls|csv)$/i, '')
    .replace(/[-_]/g, ' ')
    .replace(/\b(rent roll|lease|boma|feb|jan|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4}|\(\d+\))/gi, '')
    .trim() || 'Uploaded Property'

  const tenants: Tenant[] = [
    { id: 't-001', name: 'Anchor Tenant Corp', suite: '100', rsf: 8500, bomaRsf: 9200, rsfDelta: 700, monthlyRent: 8925, annualRent: 107100, rentPSF: 12.6, leaseStart: '2021-03-01', leaseExpiry: '2031-02-28', monthsRemaining: 58, incomeConcentration: 35, riskLevel: 'LOW', arStatus: 'CURRENT', arBalance: 0 },
    { id: 't-002', name: 'Regional Services LLC', suite: '200', rsf: 4200, bomaRsf: 4600, rsfDelta: 400, monthlyRent: 4620, annualRent: 55440, rentPSF: 13.2, leaseStart: '2022-06-01', leaseExpiry: '2027-05-31', monthsRemaining: 13, incomeConcentration: 18, riskLevel: 'MEDIUM', arStatus: 'CURRENT', arBalance: 0 },
    { id: 't-003', name: 'Local Retail Inc', suite: '105', rsf: 3100, bomaRsf: 3400, rsfDelta: 300, monthlyRent: 3410, annualRent: 40920, rentPSF: 13.2, leaseStart: '2023-01-15', leaseExpiry: '2028-01-14', monthsRemaining: 20, incomeConcentration: 13, riskLevel: 'LOW', arStatus: 'CURRENT', arBalance: 0 },
  ]

  const redFlags: RedFlag[] = [
    { id: 'rf-001', severity: 'HIGH', category: 'Near-term Rollover', description: '1 tenant with lease expiring within 12 months', impact: '18% of income at risk', resolution: 'Request renewal status' },
    { id: 'rf-002', severity: 'MEDIUM', category: 'Missing Documents', description: 'No lease documents uploaded', impact: 'Cannot verify lease terms', resolution: 'Upload executed leases' },
  ]

  return {
    id: dealId,
    dealName: propertyName,
    propertyAddress: `${propertyName}, FL`,
    submittedAt: now,
    score: 55,
    tier: 'YELLOW',
    dealReadiness: 'Proceed with conditions',
    subScores: { dataCompleteness: 12, rsfAlignment: 10, financialIntegrity: 12, leaseLeverage: 8, riskProfile: 8, documentCoverage: 10 },
    rsfReconciliation: { bomaTotalSF: 17200, rentRollOccupiedSF: 15800, deltaSF: 1400, deltaPercent: 8.1, estimatedAnnualRecovery: 16100, alertTriggered: true },
    financialSummary: { totalAnnualRent: 203460, noi: 146492, capRate: 7.8, averageRentPSF: 12.9, vacancy: 8.1, arDelinquency: 0 },
    walt: 30,
    redFlags,
    whatToGetNext: ['Executed lease documents', 'BOMA measurement report', 'AR aging report'],
    tenants,
    leaseAbstracts: [],
    documents: documents.map((d, i) => ({ id: d.id || `doc-${i}`, filename: d.filename, type: 'RENT_ROLL' as const, uploadedAt: now, pageCount: 5, status: 'PROCESSED' as const })),
  }
}
