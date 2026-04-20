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
import type { Tenant } from '@/lib/types'

interface ScoreHistoryProps {
  hasRealData?: boolean
  currentScore?: number
}

export function ScoreHistoryChart({ hasRealData, currentScore = 0 }: ScoreHistoryProps) {
  // If we have real data, show single point with current score
  // Otherwise show placeholder
  const data = hasRealData 
    ? [{ date: new Date().toISOString(), score: currentScore, docs: 1 }]
    : []

  if (!hasRealData || data.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-4">
          <h3 className="font-semibold">Score History</h3>
          <p className="text-xs text-muted-foreground">Score progression as documents are added</p>
        </div>
        <div className="flex h-48 items-center justify-center text-muted-foreground">
          <p className="text-sm">Upload more documents to see score history</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Score History</h3>
        <p className="text-xs text-muted-foreground">Score progression as documents are added</p>
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
              contentStyle={{
                backgroundColor: 'oklch(0.16 0.005 280)',
                border: '1px solid oklch(0.26 0 0)',
                borderRadius: '6px',
                color: 'oklch(0.95 0 0)',
              }}
              labelFormatter={(value) => {
                const date = new Date(value)
                return date.toLocaleDateString()
              }}
              formatter={(value: number, name: string) => {
                if (name === 'score') return [value, 'Score']
                return [value, 'Documents']
              }}
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

interface IncomeConcentrationProps {
  tenants?: Tenant[]
  hasRealData?: boolean
}

const CHART_COLORS = [
  'oklch(0.60 0.18 250)',
  'oklch(0.65 0.18 280)',
  'oklch(0.55 0.18 200)',
  'oklch(0.60 0.15 320)',
  'oklch(0.50 0.12 180)',
]

export function IncomeConcentrationChart({ tenants = [], hasRealData }: IncomeConcentrationProps) {
  // Calculate income concentration from real tenant data
  const totalRent = tenants.reduce((sum, t) => sum + (t.annualRent || 0), 0)
  
  const chartData = totalRent > 0 
    ? tenants
        .filter(t => t.annualRent > 0)
        .sort((a, b) => b.annualRent - a.annualRent)
        .slice(0, 5)
        .map((t, i) => ({
          name: t.name,
          value: Math.round((t.annualRent / totalRent) * 100),
          fill: CHART_COLORS[i % CHART_COLORS.length],
        }))
    : []

  if (!hasRealData || chartData.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-4">
          <h3 className="font-semibold">Income Concentration</h3>
          <p className="text-xs text-muted-foreground">Revenue distribution by tenant</p>
        </div>
        <div className="flex h-48 items-center justify-center text-muted-foreground">
          <p className="text-sm text-center">No tenant rent data available.<br />Upload a rent roll to see distribution.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Income Concentration</h3>
        <p className="text-xs text-muted-foreground">Revenue distribution by tenant</p>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={70}
              paddingAngle={2}
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                backgroundColor: 'oklch(0.16 0.005 280)',
                border: '1px solid oklch(0.26 0 0)',
                borderRadius: '6px',
                color: 'oklch(0.95 0 0)',
              }}
              formatter={(value: number) => [`${value}%`, 'Share']}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-2 flex flex-wrap justify-center gap-x-4 gap-y-1">
        {chartData.slice(0, 4).map((entry, index) => (
          <div key={index} className="flex items-center gap-1.5 text-xs">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.fill }} />
            <span className="text-muted-foreground">{entry.name}</span>
            <span className="font-medium">{entry.value}%</span>
          </div>
        ))}
      </div>
    </div>
  )
}

interface WALTTimelineProps {
  tenants?: Tenant[]
  hasRealData?: boolean
}

export function WALTTimelineChart({ tenants = [], hasRealData }: WALTTimelineProps) {
  // Calculate lease expiry timeline from real tenant data
  const now = new Date()
  
  const expiryData = tenants
    .filter(t => t.leaseExpiry)
    .map(t => {
      const expiry = new Date(t.leaseExpiry!)
      return {
        tenant: t.name,
        expiry,
        rent: t.annualRent || 0,
        monthsRemaining: t.monthsRemaining || Math.ceil((expiry.getTime() - now.getTime()) / (1000 * 60 * 60 * 24 * 30)),
      }
    })
    .sort((a, b) => a.expiry.getTime() - b.expiry.getTime())
    .slice(0, 5)

  const chartData = expiryData.map(t => ({
    month: t.expiry.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
    atRisk: t.rent,
    secure: 0,
    tenant: t.tenant,
  }))

  if (!hasRealData || chartData.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-4">
        <div className="mb-4">
          <h3 className="font-semibold">Lease Expiry Timeline</h3>
          <p className="text-xs text-muted-foreground">Income at risk over time</p>
        </div>
        <div className="flex h-48 items-center justify-center text-muted-foreground">
          <p className="text-sm text-center">No lease expiry data available.<br />Upload leases to see timeline.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Lease Expiry Timeline</h3>
        <p className="text-xs text-muted-foreground">Income at risk over time</p>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical">
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
              contentStyle={{
                backgroundColor: 'oklch(0.16 0.005 280)',
                border: '1px solid oklch(0.26 0 0)',
                borderRadius: '6px',
                color: 'oklch(0.95 0 0)',
              }}
              formatter={(value: number) => [`$${value.toLocaleString()}`, 'Annual Rent']}
            />
            <Bar dataKey="atRisk" fill="oklch(0.55 0.22 25)" name="At Risk" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
