import { NextRequest, NextResponse } from 'next/server'
import { store } from '@/lib/store'
import { extractJSON } from '@/lib/ai-client'
import type { AnalysisResult } from '@/lib/api'

// ─── Agent prompts ────────────────────────────────────────────────────────────

const RENT_ROLL_PROMPT = `You are a commercial real estate rent roll analyst.
Extract all tenant information from the provided document text.
For each tenant also extract usable square footage (USF) if available — if only RSF is present, estimate USF as RSF / 1.15.
Compute implied load factor as RSF / USF. Compute pro-rata share as tenant RSF / total building RSF.
Return JSON with this exact shape:
{
  "tenants": [
    {
      "tenant_name": string,
      "suite": string,
      "usf": number,
      "rsf": number,
      "load_factor": number,
      "pro_rata_share": number,
      "monthly_rent": number,
      "annual_rent": number,
      "rent_psf": number,
      "lease_start": "YYYY-MM-DD",
      "lease_end": "YYYY-MM-DD or null",
      "renewal_option": boolean,
      "ar_status": "CURRENT" | "DELINQUENT" | "AT_RISK",
      "ar_balance": number
    }
  ],
  "summary": {
    "total_building_rsf": number,
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
Extract all key lease terms AND all CAM/expense recovery provisions from the provided document text.
Pay close attention to:
- Load factor stated in the lease (also called add-on factor or common area factor)
- Usable square footage (USF) and rentable square footage (RSF) as defined in the lease
- CAM cap: annual percentage limit on CAM increases (e.g. 5%)
- Gross-up clause: expenses grossed up when occupancy falls below a threshold (typically 95%)
- Expense exclusions: GL categories explicitly excluded (capex, management fees, leasing commissions, etc.)
- Management fee cap: max recoverable management fee as a percentage
- Base year stop: tenant pays only increases above the base year amount
- Fixed vs. reconciling CAM: fixed means flat monthly with no annual true-up
- Controllable CAM cap: cap applies only to controllable expenses (taxes and insurance excluded)
- Anchor exclusion: anchor tenant SF excluded from denominator calculation
Return JSON with this exact shape:
{
  "leases": [
    {
      "tenant_name": string,
      "suite": string,
      "usf": number,
      "rsf": number,
      "load_factor": number | null,
      "lease_start": "YYYY-MM-DD",
      "lease_end": "YYYY-MM-DD or null",
      "base_rent_psf": number,
      "annual_base_rent": number,
      "rent_escalation": string,
      "expense_structure": "NNN" | "GROSS" | "MODIFIED_GROSS",
      "cam_cap": number | null,
      "cam_gross_up": boolean,
      "gross_up_threshold": number | null,
      "expense_exclusions": [string],
      "mgmt_fee_cap": number | null,
      "base_year": number | null,
      "fixed_cam": boolean,
      "controllable_cam_cap": number | null,
      "anchor_exclusion": boolean,
      "renewal_options": string | null,
      "ti_allowance": number | null,
      "remeasurement_rights": boolean,
      "missing_fields": [string]
    }
  ]
}`

const RSF_RECONCILIATION_PROMPT = `You are a commercial real estate RSF and load factor reconciliation specialist.
Your job is the most important audit in this analysis. Reconcile all square footage data across every document.
For each tenant compare:
1. RSF on the rent roll
2. RSF stated in the executed lease
3. USF from floor plans or BOMA measurements
4. Load factor implied by the rent roll (RSF / USF)
5. Load factor stated in the executed lease
Identify any tenant where the implied load factor differs from the lease-stated load factor.
Calculate the annual revenue impact of any RSF discrepancy using the tenant's in-place rent PSF.
Return JSON with this exact shape:
{
  "reconciliation": {
    "total_rsf_rent_roll": number,
    "total_rsf_leases": number,
    "total_rsf_boma": number,
    "total_usf": number,
    "variance_rent_roll_vs_boma": number,
    "variance_percentage": number,
    "estimated_annual_revenue_impact": number
  },
  "by_tenant": [
    {
      "tenant_name": string,
      "suite": string,
      "usf": number,
      "rsf_rent_roll": number,
      "rsf_lease": number,
      "rsf_boma": number,
      "load_factor_implied": number,
      "load_factor_lease": number | null,
      "load_factor_delta": number | null,
      "delta": number,
      "annual_revenue_impact": number
    }
  ]
}`

const CAM_RECONCILIATION_PROMPT = `You are a commercial real estate CAM reconciliation specialist.
Using the lease terms, rent roll, and any operating expense or financial data provided, calculate the correct CAM charge for each tenant.
Apply each lease's specific provisions: CAM caps, gross-up clauses, expense exclusions, management fee caps, base year stops, controllable caps, and anchor exclusions.
If operating expense data is unavailable, estimate total recoverable expenses based on market norms ($4-7/SF for retail, $3-5/SF for office, $1.50-3/SF for industrial).
Return JSON with this exact shape:
{
  "cam_summary": {
    "total_recoverable_expenses": number,
    "building_total_rsf": number,
    "total_cam_billed": number,
    "total_cam_owed": number,
    "over_under_collection": number
  },
  "expense_categories": [
    {
      "gl_code": string,
      "description": string,
      "total_amount": number,
      "recoverable": boolean,
      "exclusion_reason": string | null
    }
  ],
  "tenant_cam": [
    {
      "tenant_name": string,
      "suite": string,
      "usf": number,
      "rsf": number,
      "load_factor": number,
      "lease_load_factor": number | null,
      "load_factor_delta": number | null,
      "pro_rata_share": number,
      "total_recoverable_expenses": number,
      "cam_owed": number,
      "cam_billed": number,
      "over_under": number,
      "cam_cap": number | null,
      "cam_cap_applied": boolean,
      "gross_up_applied": boolean,
      "expense_exclusions": [string],
      "mgmt_fee_cap_pct": number | null,
      "base_year": number | null,
      "fixed_cam": boolean,
      "controllable_cap": number | null,
      "anchor_exclusion": boolean
    }
  ]
}`

const RED_FLAG_PROMPT = `You are a commercial real estate risk analyst.
Identify all red flags and risks in the provided deal information.
Pay special attention to:
- Load factor discrepancies between rent roll and lease
- RSF discrepancies between rent roll, lease, and floor plan
- Incorrect CAM calculations or missing expense recovery
- Near-term lease expirations (under 12 months)
- Tenant concentration risk (single tenant > 25% of income)
- Missing lease provisions (no CAM cap, no gross-up, missing expense categories)
- AR delinquency
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
Weight load factor accuracy and CAM reconciliation heavily — these are the core audit objectives.
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

function safeStr(v: unknown, fallback = ''): string {
  return v != null ? String(v) : fallback
}

function safeArr(v: unknown): unknown[] {
  return Array.isArray(v) ? v : []
}

// ─── Route ────────────────────────────────────────────────────────────────────

export async function POST(req: NextRequest) {
  try {
    const body = await req.json() as {
      deal_id: string
      documents: string[]
      known_sf?: { boma_sf?: number | null; rent_roll_sf?: number | null; lease_sf?: number | null }
      deal_name?: string
    }
    const { deal_id, documents: docIds, known_sf, deal_name } = body

    if (!deal_id || !docIds?.length) {
      return NextResponse.json({ detail: 'deal_id and documents are required' }, { status: 400 })
    }

    const docs = docIds.map((id) => store.documents.get(id)).filter(Boolean)
    if (!docs.length) {
      return NextResponse.json({ detail: 'No documents found for provided IDs' }, { status: 400 })
    }

    const allText = docs
      .map((d) => `=== ${d!.filename} (${d!.document_type}) ===\n${d!.content}`)
      .join('\n\n')

    // Run all six agents in parallel
    const [rentRollRaw, leaseRaw, rsfRaw, camRaw, redFlagRaw, riskRaw] = await Promise.allSettled([
      extractJSON<{ tenants: unknown[]; summary: Record<string, number> }>(RENT_ROLL_PROMPT, allText),
      extractJSON<{ leases: unknown[] }>(LEASE_ABSTRACTION_PROMPT, allText),
      extractJSON<{ reconciliation: Record<string, number>; by_tenant: unknown[] }>(RSF_RECONCILIATION_PROMPT, allText),
      extractJSON<{ cam_summary: Record<string, number>; expense_categories: unknown[]; tenant_cam: unknown[] }>(CAM_RECONCILIATION_PROMPT, allText),
      extractJSON<{ red_flags: unknown[] }>(RED_FLAG_PROMPT, allText),
      extractJSON<{ deal_score: Record<string, unknown>; score_factors: unknown[]; what_to_request_next: string[] }>(RISK_SCORING_PROMPT, allText),
    ])

    const rentRoll = rentRollRaw.status === 'fulfilled' ? rentRollRaw.value : { tenants: [], summary: {} }
    const leases   = leaseRaw.status === 'fulfilled'   ? leaseRaw.value   : { leases: [] }
    const rsf      = rsfRaw.status === 'fulfilled'     ? rsfRaw.value     : { reconciliation: {}, by_tenant: [] }
    const cam      = camRaw.status === 'fulfilled'     ? camRaw.value     : { cam_summary: {}, expense_categories: [], tenant_cam: [] }
    const redFlags = redFlagRaw.status === 'fulfilled' ? redFlagRaw.value : { red_flags: [] }
    const risk     = riskRaw.status === 'fulfilled'    ? riskRaw.value    : { deal_score: {}, score_factors: [], what_to_request_next: [] }

    const summary = rentRoll.summary ?? {}
    const dealScore = (risk.deal_score ?? {}) as Record<string, unknown>
    const subScores = (dealScore.sub_scores ?? {}) as Record<string, number>

    // Merge known_sf overrides
    const reconciliation = { ...(rsf.reconciliation ?? {}) }
    if (known_sf?.boma_sf) reconciliation.total_rsf_boma = known_sf.boma_sf
    if (known_sf?.rent_roll_sf) reconciliation.total_rsf_rent_roll = known_sf.rent_roll_sf
    if (known_sf?.lease_sf) reconciliation.total_rsf_leases = known_sf.lease_sf

    const bomaVal = safeNum(reconciliation.total_rsf_boma)
    const rrVal = safeNum(reconciliation.total_rsf_rent_roll)
    if (bomaVal && rrVal) {
      reconciliation.variance_rent_roll_vs_boma = rrVal - bomaVal
      reconciliation.variance_percentage = bomaVal > 0 ? ((rrVal - bomaVal) / bomaVal) * 100 : 0
    }

    // ── Build tenants ─────────────────────────────────────────────────────────
    const tenants = (safeArr(rentRoll.tenants) as Array<Record<string, unknown>>).map((t, i) => {
      const annualRent = safeNum(t.annual_rent, safeNum(t.monthly_rent) * 12)
      const rsf_ = safeNum(t.rsf, 1)
      const usf_ = safeNum(t.usf, rsf_ / 1.15)
      const loadFactor = usf_ > 0 ? rsf_ / usf_ : 1.0
      return {
        id: `t-${String(i + 1).padStart(3, '0')}`,
        name: safeStr(t.tenant_name, 'Unknown'),
        suite: safeStr(t.suite),
        usf: usf_,
        rsf: rsf_,
        loadFactor: Math.round(loadFactor * 10000) / 10000,
        leaseLoadFactor: null as number | null,
        proRataShare: safeNum(t.pro_rata_share),
        monthlyRent: safeNum(t.monthly_rent),
        annualRent,
        rentPSF: safeNum(t.rent_psf, rsf_ > 0 ? annualRent / rsf_ : 0),
        leaseStart: safeStr(t.lease_start),
        leaseExpiry: t.lease_end ? safeStr(t.lease_end) : null,
        monthsRemaining: t.lease_end
          ? Math.max(0, Math.round((new Date(safeStr(t.lease_end)).getTime() - Date.now()) / (1000 * 60 * 60 * 24 * 30)))
          : null,
        incomeConcentration: 0,
        riskLevel: 'LOW' as const,
        arStatus: (['CURRENT', 'DELINQUENT', 'AT_RISK'].includes(safeStr(t.ar_status).toUpperCase())
          ? safeStr(t.ar_status).toUpperCase()
          : 'CURRENT') as 'CURRENT' | 'DELINQUENT' | 'AT_RISK',
        arBalance: safeNum(t.ar_balance),
      }
    })

    const totalRent = tenants.reduce((s, t) => s + t.annualRent, 0) || 1
    tenants.forEach((t) => {
      t.incomeConcentration = Math.round((t.annualRent / totalRent) * 100)
      if (t.incomeConcentration > 30) t.riskLevel = 'HIGH'
      else if (t.monthsRemaining !== null && t.monthsRemaining <= 12) t.riskLevel = 'MEDIUM'
    })

    // ── Build lease abstracts ─────────────────────────────────────────────────
    const leaseAbstracts = (safeArr(leases.leases) as Array<Record<string, unknown>>).map((la, i) => {
      const rsf_ = safeNum(la.rsf)
      const usf_ = safeNum(la.usf, rsf_ / 1.15)
      return {
        id: `la-${String(i + 1).padStart(3, '0')}`,
        tenantName: safeStr(la.tenant_name, 'Unknown'),
        suite: safeStr(la.suite),
        usf: usf_,
        rsf: rsf_,
        loadFactor: la.load_factor != null ? safeNum(la.load_factor) : null,
        commencementDate: safeStr(la.lease_start),
        expirationDate: la.lease_end ? safeStr(la.lease_end) : null,
        baseRent: safeNum(la.annual_base_rent),
        escalation: safeStr(la.rent_escalation, 'Unknown'),
        expenseStructure: (['NNN', 'GROSS', 'MODIFIED_GROSS'].includes(safeStr(la.expense_structure))
          ? safeStr(la.expense_structure)
          : 'NNN') as 'NNN' | 'GROSS' | 'MODIFIED_GROSS',
        camCap: la.cam_cap != null ? safeNum(la.cam_cap) : null,
        camGrossUp: Boolean(la.cam_gross_up),
        grossUpThreshold: la.gross_up_threshold != null ? safeNum(la.gross_up_threshold) : null,
        expenseExclusions: safeArr(la.expense_exclusions).map(String),
        mgmtFeeCap: la.mgmt_fee_cap != null ? safeNum(la.mgmt_fee_cap) : null,
        baseYear: la.base_year != null ? safeNum(la.base_year) : null,
        fixedCAM: Boolean(la.fixed_cam),
        controllableCamCap: la.controllable_cam_cap != null ? safeNum(la.controllable_cam_cap) : null,
        anchorExclusion: Boolean(la.anchor_exclusion),
        renewalOptions: la.renewal_options ? safeStr(la.renewal_options) : null,
        tiAllowance: la.ti_allowance != null ? safeNum(la.ti_allowance) : null,
        remeasurementRights: Boolean(la.remeasurement_rights),
        missingFields: safeArr(la.missing_fields).map(String),
      }
    })

    // ── Build CAM reconciliation ──────────────────────────────────────────────
    const camSummary = (cam.cam_summary ?? {}) as Record<string, number>
    const camReconciliation = {
      totalRecoverableExpenses: safeNum(camSummary.total_recoverable_expenses),
      buildingTotalRSF: safeNum(camSummary.building_total_rsf, safeNum(reconciliation.total_rsf_rent_roll)),
      totalBilled: safeNum(camSummary.total_cam_billed),
      totalOwed: safeNum(camSummary.total_cam_owed),
      overUnderCollection: safeNum(camSummary.over_under_collection),
      expenseCategories: (safeArr(cam.expense_categories) as Array<Record<string, unknown>>).map((ec) => ({
        glCode: safeStr(ec.gl_code),
        description: safeStr(ec.description),
        totalAmount: safeNum(ec.total_amount),
        recoverable: Boolean(ec.recoverable),
        exclusionReason: ec.exclusion_reason ? safeStr(ec.exclusion_reason) : null,
      })),
      tenantCAMSummary: (safeArr(cam.tenant_cam) as Array<Record<string, unknown>>).map((tc) => {
        const rsf_ = safeNum(tc.rsf)
        const usf_ = safeNum(tc.usf, rsf_ / 1.15)
        return {
          tenantId: safeStr(tc.tenant_name).toLowerCase().replace(/\s+/g, '-'),
          tenantName: safeStr(tc.tenant_name),
          suite: safeStr(tc.suite),
          usf: usf_,
          rsf: rsf_,
          loadFactor: safeNum(tc.load_factor, usf_ > 0 ? rsf_ / usf_ : 1.0),
          leaseLoadFactor: tc.lease_load_factor != null ? safeNum(tc.lease_load_factor) : null,
          loadFactorDelta: tc.load_factor_delta != null ? safeNum(tc.load_factor_delta) : null,
          proRataShare: safeNum(tc.pro_rata_share),
          totalRecoverableExpenses: safeNum(tc.total_recoverable_expenses),
          camOwed: safeNum(tc.cam_owed),
          camBilled: safeNum(tc.cam_billed),
          overUnder: safeNum(tc.over_under),
          camCap: tc.cam_cap != null ? safeNum(tc.cam_cap) : null,
          camCapApplied: Boolean(tc.cam_cap_applied),
          grossUpApplied: Boolean(tc.gross_up_applied),
          expenseExclusions: safeArr(tc.expense_exclusions).map(String),
          mgmtFeeCapPct: tc.mgmt_fee_cap_pct != null ? safeNum(tc.mgmt_fee_cap_pct) : null,
          baseYear: tc.base_year != null ? safeNum(tc.base_year) : null,
          fixedCAM: Boolean(tc.fixed_cam),
          controllableCap: tc.controllable_cap != null ? safeNum(tc.controllable_cap) : null,
          anchorExclusion: Boolean(tc.anchor_exclusion),
        }
      }),
    }

    // ── Build red flags ───────────────────────────────────────────────────────
    const redFlagList = (safeArr(redFlags.red_flags) as Array<Record<string, unknown>>).map((rf) => ({
      id: safeStr(rf.id, crypto.randomUUID()),
      severity: (['HIGH', 'MEDIUM', 'LOW'].includes(safeStr(rf.severity).toUpperCase())
        ? safeStr(rf.severity).toUpperCase()
        : 'MEDIUM') as 'HIGH' | 'MEDIUM' | 'LOW',
      category: safeStr(rf.category, 'General'),
      description: safeStr(rf.description),
      impact: safeStr(rf.impact ?? rf.financial_impact),
      resolution: safeStr(rf.recommended_action),
    }))

    // ── Build documents list ──────────────────────────────────────────────────
    const documentsList = docs.map((d) => ({
      id: d!.id,
      filename: d!.filename,
      type: safeStr(d!.document_type).toUpperCase() || 'LEASE',
      uploadedAt: d!.uploaded_at,
      pageCount: d!.page_count ?? 0,
      status: 'PROCESSED' as const,
    }))

    // ── Score + tier ──────────────────────────────────────────────────────────
    const overallScore = safeNum(dealScore.overall_score, 70)
    const tierRaw = safeStr(dealScore.tier)
    const tier = (['GREEN', 'YELLOW', 'ORANGE', 'RED'].includes(tierRaw)
      ? tierRaw
      : overallScore >= 90 ? 'GREEN'
      : overallScore >= 75 ? 'YELLOW'
      : overallScore >= 60 ? 'ORANGE'
      : 'RED') as 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'

    const propertyName = deal_name || docs[0]?.filename.replace(/\.[^.]+$/, '') ?? 'Property Analysis'

    const result = {
      // Raw shape for store compatibility
      deal_id,
      property_name: propertyName,
      property_address: '',
      analysis_date: new Date().toISOString(),

      // Flattened DealAnalysis shape returned directly to the client
      id: deal_id,
      dealName: propertyName,
      propertyAddress: '',
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
      walt: safeNum(summary.walt_months),
      camReconciliation,
      redFlags: redFlagList,
      whatToGetNext: safeArr(risk.what_to_request_next).map(String),
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
