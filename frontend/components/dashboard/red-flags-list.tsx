'use client'

import { cn } from '@/lib/utils'
import { AlertTriangle, AlertCircle, Info } from 'lucide-react'
import { RedFlag } from '@/lib/types'

interface RedFlagsListProps {
  flags: RedFlag[]
  limit?: number
}

export function RedFlagsList({ flags, limit }: RedFlagsListProps) {
  const displayFlags = limit ? flags.slice(0, limit) : flags

  const severityConfig = {
    HIGH: {
      icon: AlertTriangle,
      bg: 'bg-destructive/10',
      border: 'border-destructive/30',
      text: 'text-destructive',
      badge: 'bg-destructive/20 text-destructive',
    },
    MEDIUM: {
      icon: AlertCircle,
      bg: 'bg-warning/10',
      border: 'border-warning/30',
      text: 'text-warning',
      badge: 'bg-warning/20 text-warning',
    },
    LOW: {
      icon: Info,
      bg: 'bg-chart-1/10',
      border: 'border-chart-1/30',
      text: 'text-chart-1',
      badge: 'bg-chart-1/20 text-chart-1',
    },
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Red Flags</h3>
        <p className="text-xs text-muted-foreground">
          {flags.length} issue{flags.length !== 1 ? 's' : ''} identified
        </p>
      </div>
      <div className="divide-y divide-border">
        {displayFlags.map((flag) => {
          const config = severityConfig[flag.severity]
          const Icon = config.icon
          return (
            <div key={flag.id} className="p-4">
              <div className="flex items-start gap-3">
                <div
                  className={cn(
                    'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
                    config.bg
                  )}
                >
                  <Icon className={cn('h-4 w-4', config.text)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', config.badge)}>
                      {flag.severity}
                    </span>
                    <span className="text-xs text-muted-foreground">{flag.category}</span>
                  </div>
                  <p className="mt-1 text-sm font-medium">{flag.description}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">{flag.impact}</p>
                  {flag.resolution && (
                    <p className="mt-2 text-xs text-primary">Action: {flag.resolution}</p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
      {limit && flags.length > limit && (
        <div className="border-t border-border px-4 py-3">
          <button className="text-sm text-primary hover:underline">
            View all {flags.length} flags
          </button>
        </div>
      )}
    </div>
  )
}
