'use client'

export function WhatToGetNext({ items }: { items: string[] }) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">What to Get Next</h3>
        <p className="text-xs text-muted-foreground">Requests that would close the biggest gaps</p>
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
