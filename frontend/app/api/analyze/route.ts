import { NextRequest, NextResponse } from 'next/server'
import { DealAnalysis, Tenant, LeaseAbstract, RedFlag, UploadedDocument } from '@/lib/types'

// Simulates AI agent processing - in production this would call the Python backend
function generateAnalysis(documents: { id: string; filename: string; type: string }[]): DealAnalysis {
  const dealId = `deal-${Date.now()}`
  const now = new Date().toISOString()
  
  // Extract property name from first document filename
  const firstDoc = documents[0]?.filename || 'Unknown Property'
  const propertyName = firstDoc
    .replace(/\.(pdf|xlsx|xls|csv)$/i, '')
    .replace(/[-_]/g, ' ')
    .replace(/\b(rent roll|lease|boma|feb|jan|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|\d{4}|\(\d+\))/gi, '')
    .trim() || 'Uploaded Property'

  // Determine what document types we have
  const hasRentRoll = documents.some(d => d.type.includes('Rent Roll') || d.type.includes('Spreadsheet'))
  const hasLease = documents.some(d => d.type.includes('Lease'))
  const hasBoma = documents.some(d => d.type.includes('BOMA'))

  // Generate realistic tenants based on documents
  const tenants: Tenant[] = [
    {
      id: 't-001',
      name: 'Anchor Tenant Corp',
      suite: '100',
      rsf: 8500,
      bomaRsf: 9200,
      rsfDelta: 700,
      monthlyRent: 8925,
      annualRent: 107100,
      rentPSF: 12.6,
      leaseStart: '2021-03-01',
      leaseExpiry: '2031-02-28',
      monthsRemaining: 58,
      incomeConcentration: 35,
      riskLevel: 'LOW',
      arStatus: 'CURRENT',
      arBalance: 0,
    },
    {
      id: 't-002',
      name: 'Regional Services LLC',
      suite: '200',
      rsf: 4200,
      bomaRsf: 4600,
      rsfDelta: 400,
      monthlyRent: 4620,
      annualRent: 55440,
      rentPSF: 13.2,
      leaseStart: '2022-06-01',
      leaseExpiry: '2027-05-31',
      monthsRemaining: 13,
      incomeConcentration: 18,
      riskLevel: 'MEDIUM',
      arStatus: 'CURRENT',
      arBalance: 0,
    },
    {
      id: 't-003',
      name: 'Local Retail Inc',
      suite: '105',
      rsf: 3100,
      bomaRsf: 3400,
      rsfDelta: 300,
      monthlyRent: 3410,
      annualRent: 40920,
      rentPSF: 13.2,
      leaseStart: '2023-01-15',
      leaseExpiry: '2028-01-14',
      monthsRemaining: 20,
      incomeConcentration: 13,
      riskLevel: 'LOW',
      arStatus: 'CURRENT',
      arBalance: 0,
    },
    {
      id: 't-004',
      name: 'Professional Services Group',
      suite: '210',
      rsf: 2800,
      bomaRsf: 3100,
      rsfDelta: 300,
      monthlyRent: 2940,
      annualRent: 35280,
      rentPSF: 12.6,
      leaseStart: '2020-09-01',
      leaseExpiry: '2025-08-31',
      monthsRemaining: 4,
      incomeConcentration: 12,
      riskLevel: 'HIGH',
      arStatus: 'CURRENT',
      arBalance: 0,
    },
    {
      id: 't-005',
      name: 'Quick Serve Foods',
      suite: '115',
      rsf: 2200,
      bomaRsf: 2500,
      rsfDelta: 300,
      monthlyRent: 2750,
      annualRent: 33000,
      rentPSF: 15.0,
      leaseStart: '2024-03-01',
      leaseExpiry: '2029-02-28',
      monthsRemaining: 34,
      incomeConcentration: 11,
      riskLevel: 'LOW',
      arStatus: 'CURRENT',
      arBalance: 0,
    },
    {
      id: 't-006',
      name: 'Fitness Express',
      suite: '300',
      rsf: 3500,
      bomaRsf: 3900,
      rsfDelta: 400,
      monthlyRent: 2975,
      annualRent: 35700,
      rentPSF: 10.2,
      leaseStart: '2022-01-01',
      leaseExpiry: '2027-12-31',
      monthsRemaining: 20,
      incomeConcentration: 11,
      riskLevel: 'MEDIUM',
      arStatus: 'DELINQUENT',
      arBalance: 5950,
    },
  ]

  const totalRent = tenants.reduce((sum, t) => sum + t.annualRent, 0)
  const totalRsf = tenants.reduce((sum, t) => sum + t.rsf, 0)
  const totalBomaRsf = tenants.reduce((sum, t) => sum + (t.bomaRsf || 0), 0)

  // Generate lease abstracts
  const leaseAbstracts: LeaseAbstract[] = tenants.map((t, i) => ({
    id: `la-${i + 1}`,
    tenantName: t.name,
    suite: t.suite,
    rsf: t.rsf,
    commencementDate: t.leaseStart,
    expirationDate: t.leaseExpiry,
    baseRent: t.annualRent,
    escalation: ['3% annually', '2.5% annually', '2% annually', 'CPI'][i % 4],
    expenseStructure: ['NNN', 'NNN', 'MODIFIED_GROSS', 'NNN', 'NNN', 'MODIFIED_GROSS'][i] as 'NNN' | 'MODIFIED_GROSS' | 'GROSS',
    camCap: i % 3 === 0 ? null : (5 + i),
    renewalOptions: i % 2 === 0 ? '2 x 5-year options' : '1 x 5-year option',
    tiAllowance: 10 + (i * 5),
    remeasurementRights: i % 3 === 0,
    missingFields: hasLease ? [] : ['escalation', 'renewalOptions'],
  }))

  // Calculate RSF reconciliation
  const deltaSF = totalBomaRsf - totalRsf
  const deltaPercent = (deltaSF / totalBomaRsf) * 100

  // Generate red flags based on what's found
  const redFlags: RedFlag[] = []
  
  if (deltaPercent > 5) {
    redFlags.push({
      id: 'rf-001',
      severity: 'HIGH',
      category: 'RSF Discrepancy',
      description: `BOMA total SF exceeds rent roll occupied SF by ${deltaSF.toLocaleString()} SF (${deltaPercent.toFixed(1)}%)`,
      impact: `Potential $${Math.round(deltaSF * 11.5).toLocaleString()}/year in CAM recovery not being billed`,
      resolution: 'Request remeasurement or verify tenant SF allocations',
    })
  }

  const nearTermExpiries = tenants.filter(t => t.monthsRemaining && t.monthsRemaining < 12)
  if (nearTermExpiries.length > 0) {
    redFlags.push({
      id: 'rf-002',
      severity: 'HIGH',
      category: 'Near-term Rollover',
      description: `${nearTermExpiries.length} tenant(s) with lease expiring within 12 months`,
      impact: `${nearTermExpiries.reduce((sum, t) => sum + t.incomeConcentration, 0)}% of income at risk within year one`,
      resolution: 'Request renewal status and market rent comps',
    })
  }

  const delinquentTenants = tenants.filter(t => t.arStatus === 'DELINQUENT')
  if (delinquentTenants.length > 0) {
    redFlags.push({
      id: 'rf-003',
      severity: 'MEDIUM',
      category: 'AR Delinquency',
      description: `${delinquentTenants.length} tenant(s) with past due balances totaling $${delinquentTenants.reduce((sum, t) => sum + t.arBalance, 0).toLocaleString()}`,
      impact: 'Collection risk on outstanding receivables',
      resolution: 'Request AR aging report and payment history',
    })
  }

  // Concentration risk
  const topTwoConcentration = tenants.slice(0, 2).reduce((sum, t) => sum + t.incomeConcentration, 0)
  if (topTwoConcentration > 50) {
    redFlags.push({
      id: 'rf-004',
      severity: 'MEDIUM',
      category: 'Concentration Risk',
      description: `Top 2 tenants represent ${topTwoConcentration}% of total income`,
      impact: 'Significant exposure to tenant-specific risk',
    })
  }

  if (!hasLease) {
    redFlags.push({
      id: 'rf-005',
      severity: 'HIGH',
      category: 'Missing Documents',
      description: 'No lease documents uploaded for abstraction',
      impact: 'Cannot verify lease terms, escalations, or renewal options',
      resolution: 'Upload executed lease documents for all tenants',
    })
  }

  if (!hasBoma) {
    redFlags.push({
      id: 'rf-006',
      severity: 'MEDIUM',
      category: 'Missing Documents',
      description: 'No BOMA measurement report uploaded',
      impact: 'Cannot verify RSF calculations or identify CAM recovery opportunities',
      resolution: 'Upload certified BOMA measurement report',
    })
  }

  // Calculate score based on data completeness and flags
  const baseScore = 50
  const docBonus = documents.length * 5 // Up to 25 points for 5 docs
  const flagPenalty = redFlags.filter(f => f.severity === 'HIGH').length * 8 + 
                       redFlags.filter(f => f.severity === 'MEDIUM').length * 4
  const score = Math.max(20, Math.min(95, baseScore + docBonus - flagPenalty))

  // 4-tier scoring system
  const tier = score >= 80 ? 'GREEN' : score >= 60 ? 'YELLOW' : score >= 40 ? 'ORANGE' : 'RED'
  const dealReadiness = score >= 80 ? 'Proceed with confidence' : 
                        score >= 60 ? 'Proceed with conditions' : 
                        score >= 40 ? 'Material gaps' : 'Insufficient data'

  // Create document records
  const processedDocs: UploadedDocument[] = documents.map((d) => ({
    id: d.id,
    filename: d.filename,
    type: d.type.toUpperCase().replace(/ /g, '_') as UploadedDocument['type'],
    uploadedAt: now,
    pageCount: Math.floor(Math.random() * 20) + 2,
    status: 'PROCESSED' as const,
  }))

  // What to get next
  const whatToGetNext: string[] = []
  if (!hasLease) whatToGetNext.push('Executed lease documents for all tenants')
  if (!hasBoma) whatToGetNext.push('Certified BOMA measurement report')
  if (!hasRentRoll) whatToGetNext.push('Current rent roll with all tenant details')
  whatToGetNext.push('AR aging report with tenant payment history')
  whatToGetNext.push('CAM reconciliation for prior year')
  whatToGetNext.push('Estoppel certificates for top tenants')

  const analysis: DealAnalysis = {
    id: dealId,
    dealName: propertyName,
    propertyAddress: `${propertyName}, FL`,
    submittedAt: now,
    score,
    tier: tier as 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED',
    dealReadiness: dealReadiness as DealAnalysis['dealReadiness'],
    subScores: {
      dataCompleteness: Math.min(20, documents.length * 4),
      rsfAlignment: hasBoma ? 14 : 6,
      financialIntegrity: hasRentRoll ? 16 : 8,
      leaseLeverage: hasLease ? 14 : 6,
      riskProfile: Math.max(4, 16 - redFlags.length * 2),
      documentCoverage: Math.min(20, documents.length * 4),
    },
    rsfReconciliation: {
      bomaTotalSF: totalBomaRsf,
      rentRollOccupiedSF: totalRsf,
      deltaSF,
      deltaPercent,
      estimatedAnnualRecovery: Math.round(deltaSF * 11.5),
      alertTriggered: deltaPercent > 5,
    },
    financialSummary: {
      totalAnnualRent: totalRent,
      noi: Math.round(totalRent * 0.72),
      capRate: 7.2 + Math.random() * 1.5,
      averageRentPSF: totalRent / totalRsf,
      vacancy: ((totalBomaRsf - totalRsf) / totalBomaRsf) * 100,
      arDelinquency: delinquentTenants.reduce((sum, t) => sum + t.arBalance, 0),
    },
    walt: Math.round(tenants.reduce((sum, t) => sum + (t.monthsRemaining || 0), 0) / tenants.length),
    redFlags,
    whatToGetNext,
    tenants,
    leaseAbstracts,
    documents: processedDocs,
  }

  return analysis
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const { documents, dealName } = body

    if (!documents || !Array.isArray(documents) || documents.length === 0) {
      return NextResponse.json(
        { error: 'No documents provided for analysis' },
        { status: 400 }
      )
    }

    // Simulate processing time for AI analysis
    await new Promise(resolve => setTimeout(resolve, 2000))

    // Generate analysis
    const analysis = generateAnalysis(documents)
    
    // Override deal name if provided
    if (dealName) {
      analysis.dealName = dealName
    }

    return NextResponse.json({
      success: true,
      analysis,
    })
  } catch (error) {
    console.error('Analysis error:', error)
    return NextResponse.json(
      { error: 'Failed to run analysis' },
      { status: 500 }
    )
  }
}
