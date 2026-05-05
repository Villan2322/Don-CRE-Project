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
  Legend,
} from 'recharts'
import { scoreHistory, incomeConcentration, waltTimeline } from '@/lib/mock-data'

export function ScoreHistoryChart() {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Score History</h3>
        <p className="text-xs text-muted-foreground">Score progression as documents are added</p>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={scoreHistory}>
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

export function IncomeConcentrationChart() {
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
              data={incomeConcentration}
              cx="50%"
              cy="50%"
              innerRadius={50}
              outerRadius={70}
              paddingAngle={2}
              dataKey="value"
            >
              {incomeConcentration.map((entry, index) => (
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
        {incomeConcentration.slice(0, 4).map((entry, index) => (
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

export function WALTTimelineChart() {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-4">
        <h3 className="font-semibold">Lease Expiry Timeline</h3>
        <p className="text-xs text-muted-foreground">Income at risk over time</p>
      </div>
      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={waltTimeline} layout="vertical">
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
              formatter={(value: number) => [`$${value.toLocaleString()}`, '']}
            />
            <Bar dataKey="atRisk" stackId="a" fill="oklch(0.55 0.22 25)" name="At Risk" />
            <Bar dataKey="secure" stackId="a" fill="oklch(0.65 0.18 145)" name="Secure" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
