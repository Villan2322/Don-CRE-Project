'use client'

import { cn } from '@/lib/utils'
import { DealAnalysis } from '@/lib/types'

interface ScoreCardProps {
  deal: DealAnalysis
}

export function ScoreCard({ deal }: ScoreCardProps) {
  const tierColors = {
    GREEN: 'text-success bg-success/10 border-success/30',
    YELLOW: 'text-warning bg-warning/10 border-warning/30',
    ORANGE: 'text-chart-3 bg-chart-3/10 border-chart-3/30',
    RED: 'text-destructive bg-destructive/10 border-destructive/30',
  }

  const tierLabels = {
    GREEN: 'Proceed with Confidence',
    YELLOW: 'Proceed with Conditions',
    ORANGE: 'Material Gaps',
    RED: 'Insufficient Data',
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-balance">{deal.dealName}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{deal.propertyAddress}</p>
        </div>
        <div className="text-right">
          <div className="text-5xl font-bold tabular-nums">{deal.score}</div>
          <div className="text-sm text-muted-foreground">/ 100</div>
        </div>
      </div>
      <div className="mt-6">
        <div
          className={cn(
            'inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium',
            tierColors[deal.tier]
          )}
        >
          {deal.tier} — {tierLabels[deal.tier]}
        </div>
      </div>
      <div className="mt-6 grid grid-cols-3 gap-4 lg:grid-cols-6">
        <ScoreMetric label="Data" value={deal.subScores.dataCompleteness} max={20} />
        <ScoreMetric label="RSF" value={deal.subScores.rsfAlignment} max={20} />
        <ScoreMetric label="Financial" value={deal.subScores.financialIntegrity} max={20} />
        <ScoreMetric label="Lease" value={deal.subScores.leaseLeverage} max={20} />
        <ScoreMetric label="Risk" value={deal.subScores.riskProfile} max={15} />
        <ScoreMetric label="Coverage" value={deal.subScores.documentCoverage} max={15} />
      </div>
    </div>
  )
}

function ScoreMetric({ label, value, max }: { label: string; value: number; max: number }) {
  const percentage = (value / max) * 100
  const getBarColor = (pct: number) => {
    if (pct >= 80) return 'bg-success'
    if (pct >= 60) return 'bg-warning'
    if (pct >= 40) return 'bg-chart-3'
    return 'bg-destructive'
  }

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-muted-foreground">{label}</span>
        <span className="text-sm font-medium tabular-nums">
          {value}/{max}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full rounded-full transition-all', getBarColor(percentage))}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}
