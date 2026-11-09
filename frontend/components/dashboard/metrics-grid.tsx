'use client'

import { DollarSign, Calendar, TrendingDown, AlertCircle } from 'lucide-react'
import { money, pct, sf } from '@/lib/format'
import { DealAnalysis } from '@/lib/types'

export function MetricsGrid({ deal }: { deal: DealAnalysis }) {
  const fin = deal.financialSummary
  const metrics = [
    {
      label: 'Annual NOI',
      value: money(fin.noi),
      icon: DollarSign,
      subtext: fin.noi === null ? 'Not stated in these documents' : fin.capRate !== null ? `${fin.capRate}% cap rate` : fin.noiBasis,
      alert: false,
    },
    {
      label: 'WALT',
      value: deal.walt === null ? '—' : `${Math.round(deal.walt)} mo`,
      icon: Calendar,
      subtext: deal.walt === null ? 'No expiration dates on file' : `Rent-weighted · ${Math.round(deal.waltCoverage)}% of rent dated`,
      alert: deal.walt !== null && deal.waltCoverage < 90,
    },
    {
      label: 'Vacancy',
      value: pct(fin.vacancy),
      icon: TrendingDown,
      subtext: fin.vacancy === null ? 'Building area unknown' : `${sf(deal.vacantRsf)} SF vacant`,
      alert: (fin.vacancy ?? 0) > 10,
    },
    {
      label: 'AR 60+ Days',
      value: money(fin.arDelinquency),
      icon: AlertCircle,
      subtext: fin.arDelinquency > 0 ? `${pct((fin.arDelinquency / (fin.totalAnnualRent || 1)) * 100)} of annual rent` : 'No aged receivables reported',
      alert: fin.arDelinquency > 0,
    },
  ]

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      {metrics.map((m) => {
        const Icon = m.icon
        return (
          <div key={m.label} className="rounded-lg border border-border bg-card shadow-[0_1px_2px_rgba(11,26,58,0.04)] p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">{m.label}</span>
              <Icon className={`h-4 w-4 ${m.alert ? 'text-warning' : 'text-muted-foreground'}`} />
            </div>
            <div className="mt-2 text-2xl font-semibold tabular-nums">{m.value}</div>
            <div className="mt-1 text-xs text-muted-foreground">{m.subtext}</div>
          </div>
        )
      })}
    </div>
  )
}
