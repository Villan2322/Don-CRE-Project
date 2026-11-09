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
import { ScorePoint } from '@/lib/deal-history'
import { money } from '@/lib/format'
import { ExpiryBucket, Tenant } from '@/lib/types'

const GRID = 'var(--border)'
const AXIS = { fill: 'var(--muted-foreground)', fontSize: 11 }
const TOOLTIP = {
  backgroundColor: 'var(--popover)',
  border: '1px solid var(--border)',
  borderRadius: '6px',
  color: 'var(--popover-foreground)',
  fontSize: 12,
}
const SLICES = ['var(--chart-1)', 'var(--chart-2)', 'var(--chart-3)', 'var(--chart-4)', 'var(--chart-5)', 'var(--muted-foreground)']

function Panel({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card shadow-[0_1px_2px_rgba(11,26,58,0.04)] p-4">
      <div className="mb-4">
        <h3 className="font-semibold">{title}</h3>
        <p className="text-xs text-muted-foreground">{subtitle}</p>
      </div>
      {children}
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return <div className="flex h-48 items-center justify-center text-center text-sm text-muted-foreground">{text}</div>
}

export function ScoreHistoryChart({ points }: { points: ScorePoint[] }) {
  return (
    <Panel title="Score History" subtitle="Each run of this deal name in this browser">
      {points.length < 2 ? (
        <Empty text="Re-run this deal with more documents to see the score move." />
      ) : (
        <div className="h-48">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={points}>
              <defs>
                <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--chart-1)" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis
                dataKey="date"
                tick={AXIS}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v) => {
                  const d = new Date(v)
                  return `${d.getMonth() + 1}/${d.getDate()}`
                }}
              />
              <YAxis domain={[0, 100]} tick={AXIS} axisLine={false} tickLine={false} width={30} />
              <Tooltip
                contentStyle={TOOLTIP}
                labelFormatter={(v) => new Date(v).toLocaleString()}
                formatter={(value: number, _name, item) => [`${value} (${item.payload.documents} docs)`, 'Score']}
              />
              <Area type="monotone" dataKey="score" stroke="var(--chart-1)" strokeWidth={2} fill="url(#scoreGradient)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  )
}

export function IncomeConcentrationChart({ tenants }: { tenants: Tenant[] }) {
  const sorted = [...tenants].filter((t) => t.annualRent > 0).sort((a, b) => b.annualRent - a.annualRent)
  const top = sorted.slice(0, 5).map((t) => ({ name: t.name, value: t.incomeConcentration }))
  const rest = sorted.slice(5).reduce((sum, t) => sum + t.incomeConcentration, 0)
  const data = rest > 0 ? [...top, { name: `${sorted.length - 5} other${sorted.length - 5 === 1 ? '' : 's'}`, value: Math.round(rest * 10) / 10 }] : top

  return (
    <Panel title="Income Concentration" subtitle="Share of annual base rent by tenant">
      {data.length === 0 ? (
        <Empty text="No rent data in this package." />
      ) : (
        <>
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={data} cx="50%" cy="50%" innerRadius={45} outerRadius={65} paddingAngle={2} dataKey="value">
                  {data.map((_, i) => (
                    <Cell key={i} fill={SLICES[i % SLICES.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={TOOLTIP} formatter={(v: number) => [`${v}%`, 'Share']} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-2 space-y-1">
            {data.map((d, i) => (
              <div key={d.name} className="flex items-center gap-2 text-xs">
                <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: SLICES[i % SLICES.length] }} />
                <span className="min-w-0 flex-1 truncate text-muted-foreground">{d.name}</span>
                <span className="font-medium tabular-nums">{d.value}%</span>
              </div>
            ))}
          </div>
        </>
      )}
    </Panel>
  )
}

export function ExpiryScheduleChart({ schedule }: { schedule: ExpiryBucket[] }) {
  const data = schedule.filter((b) => b.annualRent > 0 || /^\d{4}$/.test(b.label))
  const hasRent = schedule.some((b) => b.annualRent > 0)
  const color = (label: string) =>
    label === 'Expired' || label === 'Unknown' ? 'var(--destructive)' : 'var(--chart-1)'

  return (
    <Panel title="Lease Expiry Schedule" subtitle="Annual base rent rolling each year">
      {!hasRent ? (
        <Empty text="No lease terms in this package." />
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
              <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} interval={0} />
              <YAxis
                tick={AXIS}
                axisLine={false}
                tickLine={false}
                width={44}
                tickFormatter={(v) => `$${Math.round(v / 1000)}k`}
              />
              <Tooltip
                contentStyle={TOOLTIP}
                cursor={{ fill: 'var(--muted)', opacity: 0.4 }}
                formatter={(v: number, _n, item) => [
                  `${money(v)} — ${item.payload.tenants.join(', ') || 'none'}`,
                  'Rent rolling',
                ]}
              />
              <Bar dataKey="annualRent" radius={[3, 3, 0, 0]}>
                {data.map((b) => (
                  <Cell key={b.label} fill={color(b.label)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Panel>
  )
}
