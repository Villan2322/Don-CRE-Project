'use client'

import { cn } from '@/lib/utils'
import { money, monthYear, sf, term } from '@/lib/format'
import { Tenant } from '@/lib/types'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'

const RISK = {
  LOW: 'bg-success-soft text-success border-success/30',
  MEDIUM: 'bg-warning-soft text-warning border-warning/30',
  HIGH: 'bg-destructive-soft text-destructive border-destructive/30',
}

export function TenantTable({ tenants }: { tenants: Tenant[] }) {
  if (tenants.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        No rent roll or leases in this package.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Tenants</h3>
        <p className="text-xs text-muted-foreground">
          {tenants.length} tenants · RSF from the rent roll, BOMA from the measurement report
        </p>
      </div>
      {/* Phones and iPads in portrait: one card per tenant, nothing to swipe sideways. */}
      <ul className="divide-y divide-border min-[1100px]:hidden">
        {tenants.map((t) => (
          <TenantCard key={t.id} t={t} />
        ))}
      </ul>
      <div className="hidden overflow-x-auto min-[1100px]:block">
        <Table className="text-[13px]">
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-[150px]">Tenant</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead className="text-right">RSF</TableHead>
              <TableHead className="text-right">BOMA RSF</TableHead>
              <TableHead className="text-right">Delta</TableHead>
              <TableHead className="text-right">Rent/SF</TableHead>
              <TableHead className="text-right">Annual</TableHead>
              <TableHead className="text-right">Expires</TableHead>
              <TableHead className="text-right">Income %</TableHead>
              <TableHead>AR</TableHead>
              <TableHead>Risk</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tenants.map((t) => {
              const expired = t.monthsRemaining !== null && t.monthsRemaining < 0
              return (
                <TableRow key={t.id}>
                  <TableCell className="font-medium">
                    {t.name}
                    {!t.hasLease && <div className="text-xs font-normal text-muted-foreground">No lease on file</div>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{t.suite || '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">{sf(t.rsf)}</TableCell>
                  <TableCell className="text-right tabular-nums">{sf(t.bomaRsf)}</TableCell>
                  <TableCell
                    className={cn(
                      'text-right tabular-nums',
                      t.rsfDelta && t.rsf && Math.abs(t.rsfDelta) / t.rsf > 0.05 ? 'text-warning' : ''
                    )}
                  >
                    {t.rsfDelta === null ? '—' : `${t.rsfDelta > 0 ? '+' : ''}${sf(t.rsfDelta)}`}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{t.rentPSF ? money(t.rentPSF, 2) : '—'}</TableCell>
                  <TableCell className="text-right tabular-nums">{money(t.annualRent)}</TableCell>
                  <TableCell className="text-right">
                    {t.leaseExpiry ? (
                      <div className={cn('tabular-nums', (expired || (t.monthsRemaining ?? 99) <= 12) && 'text-warning', expired && 'text-destructive')}>
                        {monthYear(t.leaseExpiry)}
                        <div className="text-xs text-muted-foreground">{term(t.monthsRemaining)}</div>
                      </div>
                    ) : t.monthToMonth ? (
                      <span className="text-warning">Month-to-month</span>
                    ) : (
                      <span className="text-destructive">Unknown</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{t.incomeConcentration}%</TableCell>
                  <TableCell>
                    {t.arStatus === 'DELINQUENT' ? (
                      <span className="text-sm text-destructive" title={t.arNote ?? undefined}>
                        {money(t.arOver60)} 60+
                      </span>
                    ) : t.arStatus === 'AT_RISK' ? (
                      <span className="text-sm text-warning">{money(t.arBalance)} open</span>
                    ) : (
                      <span className="text-sm text-success">Current</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn('text-xs', RISK[t.riskLevel])}>
                      {t.riskLevel}
                    </Badge>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}

function Expiry({ t }: { t: Tenant }) {
  const expired = t.monthsRemaining !== null && t.monthsRemaining < 0
  if (t.leaseExpiry)
    return (
      <span className={cn('tabular-nums', (expired || (t.monthsRemaining ?? 99) <= 12) && 'text-warning', expired && 'text-destructive')}>
        {monthYear(t.leaseExpiry)} · {term(t.monthsRemaining)}
      </span>
    )
  if (t.monthToMonth) return <span className="text-warning">Month-to-month</span>
  return <span className="text-destructive">Expiry unknown</span>
}

function TenantCard({ t }: { t: Tenant }) {
  const off = t.rsfDelta !== null && t.rsf ? Math.abs(t.rsfDelta) / t.rsf > 0.05 : false
  return (
    <li className="space-y-3 p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{t.name}</p>
          <p className="text-xs text-muted-foreground">
            {t.suite || 'Suite not listed'}
            {!t.hasLease && ' · No lease on file'}
          </p>
        </div>
        <Badge variant="outline" className={cn('shrink-0 text-xs', RISK[t.riskLevel])}>
          {t.riskLevel}
        </Badge>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs text-muted-foreground">Annual rent</dt>
          <dd className="tabular-nums">{money(t.annualRent)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Rent / SF</dt>
          <dd className="tabular-nums">{t.rentPSF ? money(t.rentPSF, 2) : '—'}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">RSF → BOMA</dt>
          <dd className="tabular-nums">
            {sf(t.rsf)} → {sf(t.bomaRsf)}
            {t.rsfDelta !== null && (
              <span className={cn('ml-1 text-xs', off ? 'text-warning' : 'text-muted-foreground')}>
                ({t.rsfDelta > 0 ? '+' : ''}
                {sf(t.rsfDelta)})
              </span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Share of rent</dt>
          <dd className="tabular-nums">{t.incomeConcentration}%</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-xs text-muted-foreground">Expires</dt>
          <dd>
            <Expiry t={t} />
          </dd>
        </div>
        <div className="col-span-2">
          <dt className="text-xs text-muted-foreground">Receivables</dt>
          <dd>
            {t.arStatus === 'DELINQUENT' ? (
              <span className="text-destructive">{money(t.arOver60)} past due 60+ days</span>
            ) : t.arStatus === 'AT_RISK' ? (
              <span className="text-warning">{money(t.arBalance)} open</span>
            ) : (
              <span className="text-success">Current</span>
            )}
            {t.arNote && <p className="text-xs text-muted-foreground">{t.arNote}</p>}
          </dd>
        </div>
      </dl>
    </li>
  )
}
