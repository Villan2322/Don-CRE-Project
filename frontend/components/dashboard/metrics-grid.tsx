'use client'

import { DollarSign, Calendar, TrendingDown, AlertCircle } from 'lucide-react'
import { DealAnalysis } from '@/lib/types'

interface MetricsGridProps {
  deal: DealAnalysis
}

export function MetricsGrid({ deal }: MetricsGridProps) {
  const metrics = [
    {
      label: 'Annual NOI',
      value: `$${deal.financialSummary.noi.toLocaleString()}`,
      icon: DollarSign,
      subtext: `${deal.financialSummary.capRate}% cap rate`,
    },
    {
      label: 'WALT',
      value: `${deal.walt} mo`,
      icon: Calendar,
      subtext: 'Weighted avg lease term',
    },
    {
      label: 'Vacancy',
      value: `${deal.financialSummary.vacancy}%`,
      icon: TrendingDown,
      subtext: `${Math.round(deal.rsfReconciliation.bomaTotalSF * (deal.financialSummary.vacancy / 100)).toLocaleString()} SF`,
      alert: deal.financialSummary.vacancy > 10,
    },
    {
      label: 'AR Delinquency',
      value: `$${deal.financialSummary.arDelinquency.toLocaleString()}`,
      icon: AlertCircle,
      subtext: '60+ days past due',
      alert: deal.financialSummary.arDelinquency > 0,
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {metrics.map((metric) => {
        const Icon = metric.icon
        return (
          <div key={metric.label} className="rounded-lg border border-border bg-card p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{metric.label}</span>
              <Icon
                className={`h-4 w-4 ${metric.alert ? 'text-warning' : 'text-muted-foreground'}`}
              />
            </div>
            <div className="mt-2 text-2xl font-semibold tabular-nums">{metric.value}</div>
            <div className="mt-1 text-xs text-muted-foreground">{metric.subtext}</div>
          </div>
        )
      })}
    </div>
  )
}
