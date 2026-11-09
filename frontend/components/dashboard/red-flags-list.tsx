'use client'

import { useState } from 'react'
import { cn } from '@/lib/utils'
import { AlertTriangle, AlertCircle, Info, Sparkles } from 'lucide-react'
import { RedFlag } from '@/lib/types'

const SEVERITY = {
  HIGH: { icon: AlertTriangle, bg: 'bg-destructive-soft', text: 'text-destructive', badge: 'bg-destructive-soft text-destructive' },
  MEDIUM: { icon: AlertCircle, bg: 'bg-warning-soft', text: 'text-warning', badge: 'bg-warning-soft text-warning' },
  LOW: { icon: Info, bg: 'bg-chart-1/10', text: 'text-chart-1', badge: 'bg-chart-1/20 text-chart-1' },
}

export function RedFlagsList({ flags, limit }: { flags: RedFlag[]; limit?: number }) {
  const [expanded, setExpanded] = useState(false)
  const shown = limit && !expanded ? flags.slice(0, limit) : flags
  const high = flags.filter((f) => f.severity === 'HIGH').length

  return (
    <div className="rounded-lg border border-border bg-card shadow-[0_1px_2px_rgba(11,26,58,0.04)]">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Red Flags</h3>
        <p className="text-xs text-muted-foreground">
          {flags.length} issue{flags.length !== 1 ? 's' : ''}
          {high > 0 && ` · ${high} high severity`}
        </p>
      </div>
      {flags.length === 0 && <p className="p-4 text-sm text-muted-foreground">No issues found in these documents.</p>}
      <div className="divide-y divide-border">
        {shown.map((flag) => {
          const cfg = SEVERITY[flag.severity]
          const Icon = cfg.icon
          return (
            <div key={flag.id} className="p-4">
              <div className="flex items-start gap-3">
                <div className={cn('flex h-8 w-8 shrink-0 items-center justify-center rounded-full', cfg.bg)}>
                  <Icon className={cn('h-4 w-4', cfg.text)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn('rounded px-1.5 py-0.5 text-xs font-medium', cfg.badge)}>{flag.severity}</span>
                    <span className="text-xs text-muted-foreground">{flag.category}</span>
                    {flag.source === 'ai_review' && (
                      <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title="Raised by the AI review, not computed">
                        <Sparkles className="h-3 w-3" /> AI review
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-sm font-medium">{flag.description}</p>
                  {flag.impact && <p className="mt-0.5 text-xs text-muted-foreground">{flag.impact}</p>}
                  {flag.resolution && <p className="mt-2 text-xs text-primary">Action: {flag.resolution}</p>}
                  {flag.sourceDocuments && flag.sourceDocuments.length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">Source: {flag.sourceDocuments.join(', ')}</p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
      {limit && flags.length > limit && (
        <div className="border-t border-border px-4 py-1">
          <button className="py-2.5 text-sm text-primary hover:underline" onClick={() => setExpanded((v) => !v)}>
            {expanded ? 'Show fewer' : `View all ${flags.length} flags`}
          </button>
        </div>
      )}
    </div>
  )
}
