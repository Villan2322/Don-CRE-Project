'use client'

import { FileSearch, ArrowUpRight, CheckCircle2 } from 'lucide-react'

interface WhatToGetNextProps {
  items: string[]
}

export function WhatToGetNext({ items }: WhatToGetNextProps) {
  const normalizedItems = (items || []).filter(Boolean).map(item => {
    if (typeof item === 'string') return item
    if (typeof item === 'object' && item !== null) {
      const obj = item as Record<string, unknown>
      return (obj.document || obj.why_needed || JSON.stringify(item)) as string
    }
    return String(item)
  })

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <FileSearch className="h-4 w-4 text-muted-foreground" />
          <h3 className="font-semibold">Recommended Next Steps</h3>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5">
          Based on gaps found in this analysis — not a required document list
        </p>
      </div>

      {normalizedItems.length === 0 ? (
        <div className="flex items-center gap-3 p-4">
          <CheckCircle2 className="h-5 w-5 shrink-0 text-success" />
          <div>
            <p className="text-sm font-medium text-foreground">No gaps identified</p>
            <p className="text-xs text-muted-foreground">
              Uploaded documents provided sufficient data for this analysis
            </p>
          </div>
        </div>
      ) : (
        <ul className="divide-y divide-border">
          {normalizedItems.map((item, index) => {
            // Try to split on " — " to separate the document name from the reason
            const dashIdx = item.indexOf(' — ')
            const docName = dashIdx > -1 ? item.slice(0, dashIdx).trim() : item
            const reason  = dashIdx > -1 ? item.slice(dashIdx + 3).trim() : null

            return (
              <li key={index} className="flex items-start gap-3 p-4">
                <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-border bg-secondary text-xs font-medium text-muted-foreground">
                  {index + 1}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground">{docName}</p>
                  {reason && (
                    <p className="text-xs text-muted-foreground mt-0.5">{reason}</p>
                  )}
                </div>
                <button
                  className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                  aria-label="Request document"
                >
                  <ArrowUpRight className="h-4 w-4" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
