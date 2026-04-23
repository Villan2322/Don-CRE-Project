import { NextRequest } from 'next/server'
import { store } from '@/lib/store'
import { extractJSON } from '@/lib/ai-client'

// ─── Agent definitions ────────────────────────────────────────────────────────

const AGENTS = [
  {
    id: 'classifier',
    name: 'Document Classifier',
    description: 'Classifies each uploaded file by type',
    skipInStream: true, // runs during upload, not during analysis
  },
  {
    id: 'rent_roll',
    name: 'Rent Roll Analyst',
    description: 'Extracts tenant roster, rents, lease dates, WALT, NOI',
    prompt: `You are a commercial real estate rent roll analyst.
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
}`,
  },
  {
    id: 'lease_abstraction',
    name: 'Lease Abstraction',
    description: 'Extracts escalations, expense structure, TI, CAM caps, renewal options',
    prompt: `You are a commercial real estate lease abstraction specialist.
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
}`,
  },
  {
    id: 'rsf_reconciliation',
    name: 'RSF Reconciliation',
    description: 'Cross-checks SF across rent roll, leases, and BOMA measurement',
    prompt: `You are a commercial real estate RSF reconciliation specialist.
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
}`,
  },
  {
    id: 'red_flag',
    name: 'Red Flag Detection',
    description: 'Identifies risks: co-tenancy clauses, near-expiry leases, concentration risk',
    prompt: `You are a commercial real estate risk analyst.
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
}`,
  },
  {
    id: 'risk_scoring',
    name: 'Risk Scoring',
    description: 'Produces a 0-100 deal score, tier, 6 sub-scores, and next-step recommendations',
    prompt: `You are a commercial real estate deal scoring specialist.
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
}`,
  },
] as const

export type AgentId = (typeof AGENTS)[number]['id']

export interface AgentEvent {
  type: 'agent_start' | 'agent_complete' | 'agent_error' | 'analysis_complete' | 'analysis_error'
  agentId: AgentId
  agentName: string
  description: string
  startedAt?: number
  completedAt?: number
  durationMs?: number
  outputPreview?: string  // first 300 chars of the raw JSON
  error?: string
  result?: unknown         // full result on analysis_complete
}

function safeNum(v: unknown, fallback = 0): number {
  const n = Number(v)
  return isFinite(n) ? n : fallback
}

function preview(obj: unknown): string {
  try {
    return JSON.stringify(obj).slice(0, 300)
  } catch {
    return String(obj).slice(0, 300)
  }
}

export async function POST(req: NextRequest) {
  const body = await req.json() as {
    deal_id: string
    documents: string[]
    known_sf?: { boma_sf?: number | null; rent_roll_sf?: number | null; lease_sf?: number | null }
    deal_name?: string
  }
  const { deal_id, documents: docIds, known_sf, deal_name } = body

  if (!deal_id || !docIds?.length) {
    return new Response(JSON.stringify({ detail: 'deal_id and documents are required' }), { status: 400 })
  }

  const docs = docIds.map((id) => store.documents.get(id)).filter(Boolean)
  if (!docs.length) {
    return new Response(JSON.stringify({ detail: 'No documents found for provided IDs' }), { status: 400 })
  }

  const allText = docs
    .map((d) => `=== ${d!.filename} (${d!.document_type}) ===\n${d!.content}`)
    .join('\n\n')

  const encoder = new TextEncoder()
  const stream = new ReadableStream({
    async start(controller) {
      function emit(event: AgentEvent) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(event)}\n\n`))
      }

      try {
        // Run all agents sequentially so the UI sees each one fire in order
        const analysisAgents = AGENTS.filter((a) => !('skipInStream' in a && a.skipInStream))

        const results: Record<string, unknown> = {}

        for (const agent of analysisAgents) {
          const startedAt = Date.now()
          emit({
            type: 'agent_start',
            agentId: agent.id,
            agentName: agent.name,
            description: agent.description,
            startedAt,
          })

          try {
            const output = await extractJSON(agent.prompt, allText)
            const completedAt = Date.now()
            results[agent.id] = output
            emit({
              type: 'agent_complete',
              agentId: agent.id,
              agentName: agent.name,
              description: agent.description,
              startedAt,
              completedAt,
              durationMs: completedAt - startedAt,
              outputPreview: preview(output),
            })
          } catch (err) {
            const completedAt = Date.now()
            results[agent.id] = null
            emit({
              type: 'agent_error',
              agentId: agent.id,
              agentName: agent.name,
              description: agent.description,
              startedAt,
              completedAt,
              durationMs: completedAt - startedAt,
              error: err instanceof Error ? err.message : String(err),
            })
          }
        }

        // ─── Assemble final result ─────────────────────────────────────────────

        const rentRoll = (results.rent_roll ?? { tenants: [], summary: {} }) as { tenants: unknown[]; summary: Record<string, number> }
        const leases   = (results.lease_abstraction ?? { leases: [] }) as { leases: unknown[] }
        const rsf      = (results.rsf_reconciliation ?? { reconciliation: {}, by_tenant: [] }) as { reconciliation: Record<string, number>; by_tenant: unknown[] }
        const redFlags = (results.red_flag ?? { red_flags: [] }) as { red_flags: unknown[] }
        const risk     = (results.risk_scoring ?? { deal_score: {}, score_factors: [], what_to_request_next: [] }) as { deal_score: Record<string, unknown>; score_factors: unknown[]; what_to_request_next: string[] }

        const summary    = rentRoll.summary ?? {}
        const dealScore  = (risk.deal_score ?? {}) as Record<string, unknown>
        const subScores  = (dealScore.sub_scores ?? {}) as Record<string, number>

        const reconciliation = { ...(rsf.reconciliation ?? {}) }
        if (known_sf?.boma_sf)      reconciliation.total_rsf_boma       = known_sf.boma_sf
        if (known_sf?.rent_roll_sf) reconciliation.total_rsf_rent_roll  = known_sf.rent_roll_sf
        if (known_sf?.lease_sf)     reconciliation.total_rsf_leases     = known_sf.lease_sf

        const bomaVal = safeNum(reconciliation.total_rsf_boma)
        const rrVal   = safeNum(reconciliation.total_rsf_rent_roll)
        if (bomaVal && rrVal) {
          reconciliation.variance_rent_roll_vs_boma = rrVal - bomaVal
          reconciliation.variance_percentage = bomaVal > 0 ? ((rrVal - bomaVal) / bomaVal) * 100 : 0
        }

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
              ? Math.max(0, Math.round((new Date(String(t.lease_end)).getTime() - Date.now()) / (1000 * 60 * 60 * 24 * 30)))
              : null,
            incomeConcentration: 0,
            riskLevel: 'LOW' as const,
            arStatus: 'CURRENT' as const,
            arBalance: 0,
          }
        })

        const totalRent = tenants.reduce((s, t) => s + t.annualRent, 0) || 1
        tenants.forEach((t) => { t.incomeConcentration = Math.round((t.annualRent / totalRent) * 100) })

        const leaseAbstracts = (leases.leases as Array<Record<string, unknown>>).map((la, i) => ({
          id: `la-${String(i + 1).padStart(3, '0')}`,
          tenantName: String(la.tenant_name ?? 'Unknown'),
          suite: String(la.suite ?? ''),
          rsf: safeNum(la.rsf),
          commencementDate: String(la.lease_start ?? ''),
          expirationDate: la.lease_end ? String(la.lease_end) : null,
          baseRent: safeNum(la.annual_base_rent),
          escalation: String(la.rent_escalation ?? 'Unknown'),
          expenseStructure: (['NNN', 'GROSS', 'MODIFIED_GROSS'].includes(String(la.expense_structure)) ? String(la.expense_structure) : 'NNN') as 'NNN' | 'GROSS' | 'MODIFIED_GROSS',
          camCap: la.cam_cap != null ? safeNum(la.cam_cap) : null,
          renewalOptions: la.renewal_options ? String(la.renewal_options) : null,
          tiAllowance: la.ti_allowance != null ? safeNum(la.ti_allowance) : null,
          remeasurementRights: Boolean(la.remeasurement_rights),
          missingFields: Array.isArray(la.missing_fields) ? (la.missing_fields as string[]) : [],
        }))

        const redFlagList = (redFlags.red_flags as Array<Record<string, unknown>>).map((rf) => ({
          id: String(rf.id ?? crypto.randomUUID()),
          severity: (['HIGH', 'MEDIUM', 'LOW'].includes(String(rf.severity).toUpperCase()) ? String(rf.severity).toUpperCase() : 'MEDIUM') as 'HIGH' | 'MEDIUM' | 'LOW',
          category: String(rf.category ?? 'General'),
          description: String(rf.description ?? ''),
          impact: String(rf.impact ?? rf.financial_impact ?? ''),
          resolution: String(rf.recommended_action ?? ''),
        }))

        const documentsList = docs.map((d) => ({
          id: d!.id,
          filename: d!.filename,
          type: (d!.document_type.toUpperCase()) || 'LEASE',
          uploadedAt: d!.uploaded_at,
          pageCount: d!.page_count ?? 0,
          status: 'PROCESSED' as const,
        }))

        const overallScore = safeNum(dealScore.overall_score, 70)
        const tierRaw      = String(dealScore.tier ?? '')
        const tier = (['GREEN', 'YELLOW', 'ORANGE', 'RED'].includes(tierRaw)
          ? tierRaw
          : overallScore >= 90 ? 'GREEN' : overallScore >= 75 ? 'YELLOW' : overallScore >= 60 ? 'ORANGE' : 'RED') as 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'

        const result = {
          deal_id,
          property_name: deal_name || docs[0]?.filename.replace(/\.[^.]+$/, '') ?? 'Property Analysis',
          dealName: deal_name || docs[0]?.filename.replace(/\.[^.]+$/, '') ?? 'Property Analysis',
          submittedAt: new Date().toISOString(),
          score: overallScore,
          tier,
          subScores: {
            dataCompleteness:  safeNum(subScores.document_completeness, 70),
            rsfAlignment:      safeNum(subScores.rsf_integrity, 70),
            financialIntegrity: safeNum(subScores.income_verification, 70),
            leaseLeverage:     safeNum(subScores.lease_quality, 70),
            riskProfile:       safeNum(subScores.red_flag_impact, 70),
            documentCoverage:  safeNum(subScores.expense_analysis, 70),
          },
          rsfReconciliation: {
            bomaTotalSF:               safeNum(reconciliation.total_rsf_boma),
            rentRollOccupiedSF:        safeNum(reconciliation.total_rsf_rent_roll),
            deltaSF:                   safeNum(reconciliation.variance_rent_roll_vs_boma),
            deltaPercent:              Math.abs(safeNum(reconciliation.variance_percentage)),
            estimatedAnnualRecovery:   safeNum(reconciliation.estimated_annual_revenue_impact),
            alertTriggered:            Math.abs(safeNum(reconciliation.variance_percentage)) > 5,
          },
          financialSummary: {
            totalAnnualRent:  safeNum(summary.total_annual_rent),
            noi:              safeNum(summary.noi_estimate),
            capRate:          safeNum(summary.cap_rate_estimate),
            averageRentPSF:   safeNum(summary.average_rent_psf),
            vacancy:          safeNum(summary.vacancy_rate),
            arDelinquency:    safeNum(summary.ar_delinquency),
          },
          walt:          safeNum(summary.walt_months, 0),
          redFlags:      redFlagList,
          whatToGetNext: risk.what_to_request_next ?? [],
          leaseAbstracts,
          tenants,
          documents: documentsList,
        }

        store.deals.set(deal_id, result as never)

        emit({
          type: 'analysis_complete',
          agentId: 'risk_scoring',
          agentName: 'Analysis Complete',
          description: 'All agents finished',
          result,
        })
      } catch (err) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({
          type: 'analysis_error',
          error: err instanceof Error ? err.message : String(err),
        })}\n\n`))
      } finally {
        controller.close()
      }
    },
  })

  return new Response(stream, {
    headers: {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      Connection: 'keep-alive',
    },
  })
}
