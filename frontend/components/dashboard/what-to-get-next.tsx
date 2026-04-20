'use client'

import { CheckCircle2, Circle, ArrowUpRight } from 'lucide-react'

interface WhatToGetNextProps {
  items: string[]
}

export function WhatToGetNext({ items }: WhatToGetNextProps) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">What to Get Next</h3>
        <p className="text-xs text-muted-foreground">Prioritized document requests</p>
      </div>
      <ul className="divide-y divide-border">
        {items.map((item, index) => (
          <li key={index} className="flex items-start gap-3 p-4">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary text-xs font-medium text-primary">
              {index + 1}
            </div>
            <span className="flex-1 text-sm">{item}</span>
            <button className="text-muted-foreground transition-colors hover:text-foreground">
              <ArrowUpRight className="h-4 w-4" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
