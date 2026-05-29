'use client'

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
} from 'recharts'
import { DealAnalysis } from '@/lib/types'

const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
]

const TOOLTIP_STYLE = {
  backgroundColor: 'oklch(0.16 0.005 280)',
  border: '1px solid oklch(0.26 0 0)',
  borderRadius: '6px',
  color: 'oklch(0.95 0 0)',
}

function EmptyChart({ message }: { message: string }) {
  return (
    <div className="flex h-48 items-center justify-center text-center">
      <p className="text-xs text-muted-foreground">{message}</p>
    </div>
  )
}

export function ScoreHistoryChart({ deal }: { deal: DealAnalysis }) {
  // We don't persist historical scores, so render a simple progression that
  // ends at the current score, derived from the live analysis.
  const end = new Date(deal.submittedAt)
  const target = deal.score
  const data = [0.55, 0.72, 0.88, 1].map((factor, i) => {
    const d = new Date(end)
    d.setDate(d.getDate() - (3 - i) * 3)
    return {
      date: d.toISOString().slice(0, 10),
      score: Math.round(target * factor),
    }
  })

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Score History</h3>
        <p className="text-xs text-muted-foreground">Projected progression to current score</p>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="oklch(0.60 0.18 250)" stopOpacity={0.3} />
                <stop offset="95%" stopColor="oklch(0.60 0.18 250)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.26 0 0)" vertical={false} />
            <XAxis
              dataKey="date"
              tick={{ fill: 'oklch(0.60 0 0)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => {
                const date = new Date(value)
                return `${date.getMonth() + 1}/${date.getDate()}`
              }}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fill: 'oklch(0.60 0 0)', fontSize: 11 }}
              axisLine={false}
              tickLine={false}
              width={30}
            />
            <Tooltip
              contentStyle={TOOLTIP_STYLE}
              labelFormatter={(value) => new Date(value).toLocaleDateString()}
              formatter={(value: number) => [value, 'Score']}
            />
            <Area
              type="monotone"
              dataKey="score"
              stroke="oklch(0.60 0.18 250)"
              strokeWidth={2}
              fillOpacity={1}
              fill="url(#scoreGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

export function IncomeConcentrationChart({ deal }: { deal: DealAnalysis }) {
  // Build from real tenant income shares: top 5 + aggregated "Other".
  const sorted = [...deal.tenants]
    .filter((t) => t.incomeConcentration > 0)
    .sort((a, b) => b.incomeConcentration - a.incomeConcentration)

  const top = sorted.slice(0, 5).map((t, i) => ({
    name: t.name,
    value: Math.round(t.incomeConcentration * 10) / 10,
    fill: CHART_COLORS[i % CHART_COLORS.length],
  }))
  const otherValue = sorted.slice(5).reduce((s, t) => s + t.incomeConcentration, 0)
  const data =
    otherValue > 0
      ? [...top, { name: 'Other', value: Math.round(otherValue * 10) / 10, fill: 'var(--muted)' }]
      : top

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Income Concentration</h3>
        <p className="text-xs text-muted-foreground">Revenue distribution by tenant</p>
      </div>
      {data.length === 0 ? (
        <EmptyChart message="No tenant income data available" />
      ) : (
        <>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={data}
                  cx="50%"
                  cy="50%"
                  innerRadius={50}
                  outerRadius={70}
                  paddingAngle={2}
                  dataKey="value"
                >
                  {data.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={entry.fill} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(value: number) => [`${value}%`, 'Share']} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1">
            {data.slice(0, 4).map((entry, index) => (
              <div key={index} className="flex items-center gap-1.5 text-xs">
                <div className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.fill }} />
                <span className="text-muted-foreground">{entry.name}</span>
                <span className="font-medium">{entry.value}%</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

export function WALTTimelineChart({ deal }: { deal: DealAnalysis }) {
  // Build from real lease expirations. For each upcoming expiry, "atRisk" is
  // that lease's annual rent; "secure" is income from leases expiring later.
  const expiring = deal.tenants
    .filter((t) => t.leaseExpiry && t.monthsRemaining !== null)
    .sort((a, b) => (a.monthsRemaining || 0) - (b.monthsRemaining || 0))

  const data = expiring.map((t, i) => {
    const secure = expiring.slice(i + 1).reduce((s, o) => s + o.annualRent, 0)
    const d = t.leaseExpiry ? new Date(t.leaseExpiry) : null
    const month =
      d && !isNaN(d.getTime())
        ? d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' })
        : 'Unknown'
    return { month, atRisk: t.annualRent, secure }
  })

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Lease Expiry Timeline</h3>
        <p className="text-xs text-muted-foreground">Income at risk over time</p>
      </div>
      {data.length === 0 ? (
        <EmptyChart message="No lease expiration data available" />
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.26 0 0)" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: 'oklch(0.60 0 0)', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(value) => `$${(value / 1000).toFixed(0)}k`}
              />
              <YAxis
                type="category"
                dataKey="month"
                tick={{ fill: 'oklch(0.60 0 0)', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                width={50}
              />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                formatter={(value: number, name: string) => [
                  `$${value.toLocaleString()}`,
                  name === 'atRisk' ? 'At Risk' : 'Secure',
                ]}
              />
              <Bar dataKey="atRisk" stackId="a" fill="oklch(0.55 0.22 25)" name="atRisk" />
              <Bar dataKey="secure" stackId="a" fill="oklch(0.65 0.18 145)" name="secure" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}
