'use client'

import { ArrowUpRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'

// Support both string arrays and object arrays from the API
type WhatToGetNextItem = string | {
  document?: string
  why_needed?: string
  score_impact?: string | number
  priority?: string | number
}

interface WhatToGetNextProps {
  items: WhatToGetNextItem[]
}

function getItemText(item: WhatToGetNextItem): string {
  if (typeof item === 'string') {
    return item
  }
  return item.document || 'Unknown document'
}

function getItemReason(item: WhatToGetNextItem): string | null {
  if (typeof item === 'string') {
    return null
  }
  return item.why_needed || null
}

function getItemPriority(item: WhatToGetNextItem): string | null {
  if (typeof item === 'string') {
    return null
  }
  const priority = item.priority
  if (priority === undefined || priority === null) return null
  return String(priority)
}

function getItemImpact(item: WhatToGetNextItem): string | null {
  if (typeof item === 'string') {
    return null
  }
  const impact = item.score_impact
  if (impact === undefined || impact === null) return null
  return String(impact)
}

function getPriorityColor(priority: string | null): string {
  if (!priority) return 'bg-muted text-muted-foreground'
  const p = priority.toLowerCase()
  if (p === 'critical' || p === '1' || p === 'high') return 'bg-destructive/20 text-destructive'
  if (p === 'medium' || p === '2') return 'bg-warning/20 text-warning'
  return 'bg-muted text-muted-foreground'
}

export function WhatToGetNext({ items }: WhatToGetNextProps) {
  if (!items || items.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">What to Get Next</h3>
          <p className="text-xs text-muted-foreground">Prioritized document requests</p>
        </div>
        <div className="p-4 text-sm text-muted-foreground">
          No additional documents needed at this time.
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">What to Get Next</h3>
        <p className="text-xs text-muted-foreground">Prioritized document requests</p>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item, index) => {
          const text = getItemText(item)
          const reason = getItemReason(item)
          const priority = getItemPriority(item)
          const impact = getItemImpact(item)
          
          return (
            <li key={index} className="flex items-start gap-3 p-4">
              <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary text-xs font-medium text-primary">
                {index + 1}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{text}</span>
                  {priority && (
                    <Badge variant="outline" className={`text-xs ${getPriorityColor(priority)}`}>
                      {priority}
                    </Badge>
                  )}
                </div>
                {reason && (
                  <p className="mt-1 text-xs text-muted-foreground">{reason}</p>
                )}
                {impact && (
                  <p className="mt-1 text-xs text-primary">Score impact: +{impact} pts</p>
                )}
              </div>
              <button className="text-muted-foreground transition-colors hover:text-foreground">
                <ArrowUpRight className="h-4 w-4" />
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
