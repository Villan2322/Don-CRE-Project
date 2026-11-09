'use client'

import { cn } from '@/lib/utils'
import { money, monthYear, sf } from '@/lib/format'
import { LeaseAbstract } from '@/lib/types'
import { AlertCircle, CheckCircle2, FileText } from 'lucide-react'

const EXPENSE = { NNN: 'NNN', GROSS: 'Gross', MODIFIED_GROSS: 'Modified gross' }
const FIELD_NAMES: Record<string, string> = {
  tenant_name: 'tenant name',
  rentable_sf: 'rentable SF',
  lease_expiration_date: 'expiration date',
  base_rent_annual: 'annual rent',
}

// One card per lease: the terms are mostly text, which a wide table can't show on an iPad.
export function LeaseAbstractsTable({ abstracts }: { abstracts: LeaseAbstract[] }) {
  if (abstracts.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground shadow-[0_1px_2px_rgba(11,26,58,0.04)]">
        No leases or lease abstracts in this package.
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      {abstracts.map((a) => (
        <article key={a.id} className="min-w-0 rounded-lg border border-border bg-card shadow-[0_1px_2px_rgba(11,26,58,0.04)]">
          <header className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <h3 className="font-semibold">{a.tenantName}</h3>
              <p className="flex items-center gap-1 truncate text-xs text-muted-foreground">
                <FileText className="h-3 w-3 shrink-0" />
                <span className="truncate">{a.suite ? `${a.suite} · ` : ''}{a.sourceFile}</span>
              </p>
            </div>
            {a.missingFields.length > 0 ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-warning-soft px-2 py-0.5 text-xs font-medium text-warning">
                <AlertCircle className="h-3.5 w-3.5" />
                {a.missingFields.length} missing
              </span>
            ) : (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-success-soft px-2 py-0.5 text-xs font-medium text-success">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Complete
              </span>
            )}
          </header>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 p-4 text-sm sm:grid-cols-4">
            <Term label="Rentable SF" value={sf(a.rsf || null)} />
            <Term label="Base rent / yr" value={a.baseRent ? money(a.baseRent) : '—'} />
            <Term label="Commenced" value={monthYear(a.commencementDate)} />
            <Term
              label="Expires"
              value={a.expirationDate ? monthYear(a.expirationDate) : 'Missing'}
              className={cn(!a.expirationDate && 'text-destructive')}
            />
            <Term
              label="Expenses"
              value={a.expenseStructure ? EXPENSE[a.expenseStructure] : a.expenseStructureText ?? '—'}
              sub={a.expenseStructure ? a.expenseStructureText : null}
              wide
            />
            <Term label="Escalation" value={a.escalation} wide muted={a.escalation === 'Unknown'} />
            {a.camCap && <Term label="CAM cap" value={a.camCap} wide />}
            {a.tiAllowance ? <Term label="TI allowance" value={money(a.tiAllowance)} /> : null}
            <Term label="Remeasurement" value={a.remeasurementRights ? 'Addressed in lease' : 'Not addressed'} muted={!a.remeasurementRights} />
            <Term label="Renewal options" value={a.renewalOptions ?? '—'} full muted={!a.renewalOptions} />
          </dl>
          {a.missingFields.length > 0 && (
            <p className="border-t border-border px-4 py-2.5 text-xs text-warning">
              Missing: {a.missingFields.map((f) => FIELD_NAMES[f] ?? f.replace(/_/g, ' ')).join(', ')}
            </p>
          )}
        </article>
      ))}
    </div>
  )
}

function Term({ label, value, sub, wide, full, muted, className }: {
  label: string; value: string; sub?: string | null; wide?: boolean; full?: boolean; muted?: boolean; className?: string
}) {
  return (
    <div className={cn('min-w-0', wide && 'col-span-2', full && 'col-span-2 sm:col-span-4')}>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className={cn('tabular-nums', muted && 'text-muted-foreground', className)}>{value}</dd>
      {sub && <dd className="text-xs text-muted-foreground">{sub}</dd>}
    </div>
  )
}
