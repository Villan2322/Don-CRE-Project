'use client'

import { DollarSign, Calendar, TrendingDown, AlertCircle } from 'lucide-react'
import { DealAnalysis } from '@/lib/types'

interface MetricsGridProps {
  deal: DealAnalysis
}

export function MetricsGrid({ deal }: MetricsGridProps) {
  const { noi, capRate, vacancy, arDelinquency } = deal.financialSummary
  // Vacancy SF prefers BOMA total; falls back to rent-roll occupied SF basis
  const vacancyBasisSF =
    deal.rsfReconciliation.bomaTotalSF || deal.rsfReconciliation.rentRollOccupiedSF || 0

  const metrics = [
    {
      label: 'Annual NOI',
      value: noi !== null ? `$${noi.toLocaleString()}` : 'N/A',
      icon: DollarSign,
      subtext: capRate !== null ? `${capRate}% cap rate` : 'Needs operating statement',
    },
    {
      label: 'WALT',
      value: deal.walt > 0 ? `${deal.walt} mo` : 'N/A',
      icon: Calendar,
      subtext: 'Weighted avg lease term',
    },
    {
      label: 'Vacancy',
      value: `${vacancy}%`,
      icon: TrendingDown,
      subtext: `${Math.round(vacancyBasisSF * (vacancy / 100)).toLocaleString()} SF`,
      alert: vacancy > 10,
    },
    {
      label: 'AR Delinquency',
      value: arDelinquency !== null ? `$${arDelinquency.toLocaleString()}` : 'N/A',
      icon: AlertCircle,
      subtext: arDelinquency !== null ? '60+ days past due' : 'Needs AR aging report',
      alert: arDelinquency !== null && arDelinquency > 0,
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
