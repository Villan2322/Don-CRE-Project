'use client'

import { Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DealAnalysis, ScoreCategoryKey } from '@/lib/types'

const LABELS: Record<ScoreCategoryKey, string> = {
  dataCompleteness: 'Data',
  rsfAlignment: 'RSF',
  financialIntegrity: 'Financial',
  leaseLeverage: 'Lease',
  riskProfile: 'Risk',
  documentCoverage: 'Coverage',
}

const FULL_LABELS: Record<ScoreCategoryKey, string> = {
  dataCompleteness: 'Data completeness',
  rsfAlignment: 'RSF alignment',
  financialIntegrity: 'Financial integrity',
  leaseLeverage: 'Lease leverage',
  riskProfile: 'Risk profile',
  documentCoverage: 'Document coverage',
}

const TIER_STYLE = {
  GREEN: 'text-success bg-success/10 border-success/30',
  YELLOW: 'text-warning bg-warning/10 border-warning/30',
  ORANGE: 'text-chart-3 bg-chart-3/10 border-chart-3/30',
  RED: 'text-destructive bg-destructive/10 border-destructive/30',
}

function barColor(pct: number) {
  if (pct >= 80) return 'bg-success'
  if (pct >= 60) return 'bg-warning'
  if (pct >= 40) return 'bg-chart-3'
  return 'bg-destructive'
}

export function ScoreCard({ deal, detailed = false }: { deal: DealAnalysis; detailed?: boolean }) {
  const keys = Object.keys(LABELS) as ScoreCategoryKey[]

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-2xl font-semibold text-balance">{deal.dealName}</h2>
          {deal.propertyAddress && <p className="mt-1 text-sm text-muted-foreground">{deal.propertyAddress}</p>}
        </div>
        <div className="shrink-0 text-right">
          <div className="text-5xl font-bold tabular-nums">{deal.score}</div>
          <div className="text-sm text-muted-foreground">/ 100</div>
        </div>
      </div>
      <div className={cn('mt-4 inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium', TIER_STYLE[deal.tier])}>
        {deal.tier} — {deal.dealReadiness}
      </div>
      {deal.executiveSummary && !detailed && (
        <p className="mt-4 max-w-3xl text-sm leading-relaxed text-muted-foreground">{deal.executiveSummary}</p>
      )}

      {!detailed ? (
        <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
          {keys.map((key) => {
            const cat = deal.scoreBreakdown[key]
            const pct = cat.max ? (cat.points / cat.max) * 100 : 0
            return (
              <div key={key}>
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-muted-foreground">{LABELS[key]}</span>
                  <span className="text-sm font-medium tabular-nums">
                    {cat.points}/{cat.max}
                  </span>
                </div>
                <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div className={cn('h-full rounded-full', barColor(pct))} style={{ width: `${pct}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      ) : (
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          {keys.map((key) => {
            const cat = deal.scoreBreakdown[key]
            const pct = cat.max ? (cat.points / cat.max) * 100 : 0
            return (
              <div key={key} className="rounded-md border border-border p-4">
                <div className="flex items-baseline justify-between">
                  <span className="text-sm font-medium">{FULL_LABELS[key]}</span>
                  <span className="text-sm font-semibold tabular-nums">
                    {cat.points} / {cat.max}
                  </span>
                </div>
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div className={cn('h-full rounded-full', barColor(pct))} style={{ width: `${pct}%` }} />
                </div>
                <ul className="mt-3 space-y-1.5">
                  {cat.reasons.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-xs">
                      {r.earned ? (
                        <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-success" />
                      ) : (
                        <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive" />
                      )}
                      <span className="flex-1 text-muted-foreground">{r.text}</span>
                      <span className="tabular-nums">{r.points > 0 ? `+${r.points}` : r.points}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
