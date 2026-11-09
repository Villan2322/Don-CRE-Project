'use client'

import { Plus } from 'lucide-react'

export function WhatToGetNext({ items, onAdd }: { items: string[]; onAdd?: () => void }) {
  return (
    <div className="rounded-lg border border-border bg-card shadow-[0_1px_2px_rgba(11,26,58,0.04)]">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div>
          <h3 className="font-semibold">What to Get Next</h3>
          <p className="text-xs text-muted-foreground">Requests that would close the biggest gaps</p>
        </div>
        {onAdd && (
          <button
            onClick={onAdd}
            className="inline-flex shrink-0 items-center gap-1 rounded-md border border-border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
          >
            <Plus className="h-3.5 w-3.5" />
            Add documents
          </button>
        )}
      </div>
      {items.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">The package covers the core documents.</p>
      ) : (
        <ol className="divide-y divide-border">
          {items.map((item, i) => {
            const [what, why] = item.split(' — ')
            return (
              <li key={i} className="flex items-start gap-3 p-4">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-primary text-xs font-medium text-primary">
                  {i + 1}
                </span>
                <div className="min-w-0 text-sm">
                  <span className="font-medium">{what}</span>
                  {why && <p className="mt-0.5 text-xs text-muted-foreground">{why}</p>}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}
