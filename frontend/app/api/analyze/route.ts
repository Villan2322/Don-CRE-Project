import { NextRequest, NextResponse } from 'next/server'
import { store } from '@/lib/store'
import { extractJSON } from '@/lib/ai-client'
import type { AnalysisResult } from '@/lib/api'

// ─── Agent prompts ────────────────────────────────────────────────────────────

const RENT_ROLL_PROMPT = `You are a commercial real estate rent roll analyst.
Extract all tenant information from the provided document text.
Return JSON with this exact shape:
{
  "tenants": [
    {
      "tenant_name": string,
      "suite": string,
      "rsf": number,
      "monthly_rent": number,
      "annual_rent": number,
      "rent_psf": number,
      "lease_start": "YYYY-MM-DD",
      "lease_end": "YYYY-MM-DD or null",
      "renewal_option": boolean
    }
  ],
  "summary": {
    "total_rsf": number,
    "total_annual_rent": number,
    "average_rent_psf": number,
    "vacancy_rate": number,
    "noi_estimate": number,
    "cap_rate_estimate": number,
    "walt_months": number,
    "ar_delinquency": number
  }
}`

const LEASE_ABSTRACTION_PROMPT = `You are a commercial real estate lease abstraction specialist.
Extract all key lease terms from the provided document text.
Return JSON with this exact shape:
{
  "leases": [
    {
      "tenant_name": string,
      "suite": string,
      "rsf": number,
      "lease_start": "YYYY-MM-DD",
      "lease_end": "YYYY-MM-DD or null",
      "base_rent_psf": number,
      "annual_base_rent": number,
      "rent_escalation": string,
      "expense_structure": "NNN" | "GROSS" | "MODIFIED_GROSS",
      "cam_cap": number | null,
      "renewal_options": string | null,
      "ti_allowance": number | null,
      "remeasurement_rights": boolean,
      "missing_fields": [string]
    }
  ]
}`

const RSF_RECONCILIATION_PROMPT = `You are a commercial real estate RSF reconciliation specialist.
Compare square footage data across all provided documents.
Return JSON with this exact shape:
{
  "reconciliation": {
    "total_rsf_rent_roll": number,
    "total_rsf_leases": number,
    "total_rsf_boma": number,
    "variance_rent_roll_vs_boma": number,
    "variance_percentage": number,
    "estimated_annual_revenue_impact": number
  },
  "by_tenant": [
    {
      "tenant_name": string,
      "suite": string,
      "rsf_rent_roll": number,
      "rsf_lease": number,
      "rsf_boma": number,
      "delta": number
    }
  ]
}`

const RED_FLAG_PROMPT = `You are a commercial real estate risk analyst.
Identify all red flags and risks in the provided deal information.
Return JSON with this exact shape:
{
  "red_flags": [
    {
      "id": string,
      "category": string,
      "severity": "high" | "medium" | "low",
      "title": string,
      "description": string,
      "impact": string,
      "recommended_action": string,
      "affected_tenants": [string],
      "financial_impact": number | null
    }
  ]
}`

const RISK_SCORING_PROMPT = `You are a commercial real estate deal scoring specialist.
Score this deal from 0-100 across multiple dimensions.
Return JSON with this exact shape:
{
  "deal_score": {
    "overall_score": number,
    "tier": "GREEN" | "YELLOW" | "ORANGE" | "RED",
    "sub_scores": {
      "document_completeness": number,
      "rsf_integrity": number,
      "income_verification": number,
      "lease_quality": number,
      "red_flag_impact": number,
      "expense_analysis": number
    }
  },
  "score_factors": [
    { "category": string, "impact": number, "reason": string }
  ],
  "what_to_request_next": [string]
}`

// ─── Helper ───────────────────────────────────────────────────────────────────

function safeNum(v: unknown, fallback = 0): number {
  const n = Number(v)
  return isFinite(n) ? n : fallback
}

// ─── Route ────────────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as { deal_id: string; documents: string[] }
    const { deal_id, documents: docIds } = body

    if (!deal_id || !docIds?.length) {
      return NextResponse.json({ detail: 'deal_id and documents are required' }, { status: 400 })
    }

    // Gather document contents
    const docs = docIds.map((id) => store.documents.get(id)).filter(Boolean)
    if (!docs.length) {
      return NextResponse.json({ detail: 'No documents found for provided IDs' }, { status: 400 })
    }

    const allText = docs
      .map((d) => `=== ${d!.filename} (${d!.document_type}) ===\n${d!.content}`)
      .join('\n\n')

    // Run all agents in parallel
    const [rentRollRaw, leaseRaw, rsfRaw, redFlagRaw, riskRaw] = await Promise.allSettled([
      extractJSON<{ tenants: unknown[]; summary: Record<string, number> }>(RENT_ROLL_PROMPT, allText),
      extractJSON<{ leases: unknown[] }>(LEASE_ABSTRACTION_PROMPT, allText),
      extractJSON<{ reconciliation: Record<string, number>; by_tenant: unknown[] }>(RSF_RECONCILIATION_PROMPT, allText),
      extractJSON<{ red_flags: unknown[] }>(RED_FLAG_PROMPT, allText),
      extractJSON<{ deal_score: Record<string, unknown>; score_factors: unknown[]; what_to_request_next: string[] }>(RISK_SCORING_PROMPT, allText),
    ])

    const rentRoll = rentRollRaw.status === 'fulfilled' ? rentRollRaw.value : { tenants: [], summary: {} }
    const leases   = leaseRaw.status === 'fulfilled'   ? leaseRaw.value   : { leases: [] }
    const rsf      = rsfRaw.status === 'fulfilled'     ? rsfRaw.value     : { reconciliation: {}, by_tenant: [] }
    const redFlags = redFlagRaw.status === 'fulfilled' ? redFlagRaw.value : { red_flags: [] }
    const risk     = riskRaw.status === 'fulfilled'    ? riskRaw.value    : { deal_score: {}, score_factors: [], what_to_request_next: [] }

    const summary = rentRoll.summary ?? {}
    const dealScore = (risk.deal_score ?? {}) as Record<string, unknown>
    const subScores = (dealScore.sub_scores ?? {}) as Record<string, number>
    const reconciliation = rsf.reconciliation ?? {}

    // Build tenants list
    const tenants = (rentRoll.tenants as Array<Record<string, unknown>>).map((t, i) => {
      const annualRent = safeNum(t.annual_rent, safeNum(t.monthly_rent) * 12)
      const rsf_ = safeNum(t.rsf, 1)
      return {
        id: `t-${String(i + 1).padStart(3, '0')}`,
        name: String(t.tenant_name ?? 'Unknown'),
        suite: String(t.suite ?? ''),
        rsf: rsf_,
        monthlyRent: safeNum(t.monthly_rent),
        annualRent,
        rentPSF: safeNum(t.rent_psf, rsf_ > 0 ? annualRent / rsf_ : 0),
        leaseStart: String(t.lease_start ?? ''),
        leaseExpiry: t.lease_end ? String(t.lease_end) : null,
        monthsRemaining: t.lease_end
          ? Math.max(
              0,
              Math.round(
                (new Date(String(t.lease_end)).getTime() - Date.now()) / (1000 * 60 * 60 * 24 * 30),
              ),
            )
          : null,
        incomeConcentration: 0, // calculated below
        riskLevel: 'LOW' as const,
        arStatus: 'CURRENT' as const,
        arBalance: 0,
      }
    })

    // Calculate income concentration
    const totalRent = tenants.reduce((s, t) => s + t.annualRent, 0) || 1
    tenants.forEach((t) => {
      t.incomeConcentration = Math.round((t.annualRent / totalRent) * 100)
    })

    // Build lease abstracts
    const leaseAbstracts = (leases.leases as Array<Record<string, unknown>>).map((la, i) => ({
      id: `la-${String(i + 1).padStart(3, '0')}`,
      tenantName: String(la.tenant_name ?? 'Unknown'),
      suite: String(la.suite ?? ''),
      rsf: safeNum(la.rsf),
      commencementDate: String(la.lease_start ?? ''),
      expirationDate: la.lease_end ? String(la.lease_end) : null,
      baseRent: safeNum(la.annual_base_rent),
      escalation: String(la.rent_escalation ?? 'Unknown'),
      expenseStructure: (['NNN', 'GROSS', 'MODIFIED_GROSS'].includes(String(la.expense_structure))
        ? String(la.expense_structure)
        : 'NNN') as 'NNN' | 'GROSS' | 'MODIFIED_GROSS',
      camCap: la.cam_cap != null ? safeNum(la.cam_cap) : null,
      renewalOptions: la.renewal_options ? String(la.renewal_options) : null,
      tiAllowance: la.ti_allowance != null ? safeNum(la.ti_allowance) : null,
      remeasurementRights: Boolean(la.remeasurement_rights),
      missingFields: Array.isArray(la.missing_fields) ? (la.missing_fields as string[]) : [],
    }))

    // Build red flags
    const redFlagList = (redFlags.red_flags as Array<Record<string, unknown>>).map((rf) => ({
      id: String(rf.id ?? crypto.randomUUID()),
      severity: (['HIGH', 'MEDIUM', 'LOW'].includes(String(rf.severity).toUpperCase())
        ? String(rf.severity).toUpperCase()
        : 'MEDIUM') as 'HIGH' | 'MEDIUM' | 'LOW',
      category: String(rf.category ?? 'General'),
      description: String(rf.description ?? ''),
      impact: String(rf.impact ?? rf.financial_impact ?? ''),
      resolution: String(rf.recommended_action ?? ''),
    }))

    // Build documents list
    const documentsList = docs.map((d) => ({
      id: d!.id,
      filename: d!.filename,
      type: (d!.document_type.toUpperCase() as string) || 'LEASE',
      uploadedAt: d!.uploaded_at,
      pageCount: d!.page_count ?? 0,
      status: 'PROCESSED' as const,
    }))

    const overallScore = safeNum(dealScore.overall_score, 70)
    const tierRaw = String(dealScore.tier ?? '')
    const tier = (['GREEN', 'YELLOW', 'ORANGE', 'RED'].includes(tierRaw)
      ? tierRaw
      : overallScore >= 90 ? 'GREEN' : overallScore >= 75 ? 'YELLOW' : overallScore >= 60 ? 'ORANGE' : 'RED') as
        'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'

    const result: AnalysisResult & {
      tenants: typeof tenants
      leaseAbstracts: typeof leaseAbstracts
      redFlags: typeof redFlagList
      documents: typeof documentsList
      subScores: Record<string, number>
      score: number
      tier: typeof tier
      walt: number
      financialSummary: Record<string, number>
      whatToGetNext: string[]
      rsfReconciliation: {
        bomaTotalSF: number
        rentRollOccupiedSF: number
        deltaSF: number
        deltaPercent: number
        estimatedAnnualRecovery: number
        alertTriggered: boolean
      }
      dealName: string
      submittedAt: string
    } = {
      // Raw AnalysisResult fields (for normalize.ts compatibility)
      deal_id,
      property_name: docs[0]?.filename.replace(/\.[^.]+$/, '') ?? 'Property Analysis',
      property_address: '',
      analysis_date: new Date().toISOString(),
      deal_score: {
        overall_score: overallScore,
        tier,
        sub_scores: subScores,
        score_factors: risk.score_factors as Array<{ category: string; impact: number; reason: string }>,
      },
      rsf_reconciliation: {
        total_rsf_rent_roll: safeNum(reconciliation.total_rsf_rent_roll),
        total_rsf_leases: safeNum(reconciliation.total_rsf_leases),
        total_rsf_boma: safeNum(reconciliation.total_rsf_boma),
        variance_rent_roll_vs_boma: safeNum(reconciliation.variance_rent_roll_vs_boma),
        variance_percentage: safeNum(reconciliation.variance_percentage),
        estimated_annual_revenue_impact: safeNum(reconciliation.estimated_annual_revenue_impact),
        discrepancies: (rsf.by_tenant ?? []) as Array<Record<string, unknown>>,
      },
      tenants: [],
      lease_abstracts: [],
      red_flags: [],
      documents_processed: [],
      what_to_get_next: risk.what_to_request_next ?? [],
      financial_summary: summary,

      // Flattened DealAnalysis-shaped fields (consumed directly by normalize.ts)
      dealName: docs[0]?.filename.replace(/\.[^.]+$/, '') ?? 'Property Analysis',
      submittedAt: new Date().toISOString(),
      score: overallScore,
      tier,
      subScores: {
        dataCompleteness: safeNum(subScores.document_completeness, 70),
        rsfAlignment: safeNum(subScores.rsf_integrity, 70),
        financialIntegrity: safeNum(subScores.income_verification, 70),
        leaseLeverage: safeNum(subScores.lease_quality, 70),
        riskProfile: safeNum(subScores.red_flag_impact, 70),
        documentCoverage: safeNum(subScores.expense_analysis, 70),
      },
      rsfReconciliation: {
        bomaTotalSF: safeNum(reconciliation.total_rsf_boma),
        rentRollOccupiedSF: safeNum(reconciliation.total_rsf_rent_roll),
        deltaSF: safeNum(reconciliation.variance_rent_roll_vs_boma),
        deltaPercent: Math.abs(safeNum(reconciliation.variance_percentage)),
        estimatedAnnualRecovery: safeNum(reconciliation.estimated_annual_revenue_impact),
        alertTriggered: Math.abs(safeNum(reconciliation.variance_percentage)) > 5,
      },
      financialSummary: {
        totalAnnualRent: safeNum(summary.total_annual_rent),
        noi: safeNum(summary.noi_estimate),
        capRate: safeNum(summary.cap_rate_estimate),
        averageRentPSF: safeNum(summary.average_rent_psf),
        vacancy: safeNum(summary.vacancy_rate),
        arDelinquency: safeNum(summary.ar_delinquency),
      },
      walt: safeNum(summary.walt_months, 0),
      redFlags: redFlagList,
      whatToGetNext: risk.what_to_request_next ?? [],
      leaseAbstracts,
      tenants,
      documents: documentsList,
    }

    store.deals.set(deal_id, result as unknown as AnalysisResult)

    return NextResponse.json({
      deal_id,
      status: 'completed',
      message: 'Analysis completed successfully',
      result,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Analysis failed'
    console.error('[v0] Analysis error:', message)
    return NextResponse.json({ detail: message }, { status: 500 })
  }
}
