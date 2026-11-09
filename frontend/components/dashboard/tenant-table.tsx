'use client'

import { cn } from '@/lib/utils'
import { money, monthYear, sf, term } from '@/lib/format'
import { Tenant } from '@/lib/types'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'

const RISK = {
  LOW: 'bg-success/20 text-success border-success/30',
  MEDIUM: 'bg-warning/20 text-warning border-warning/30',
  HIGH: 'bg-destructive/20 text-destructive border-destructive/30',
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
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-[180px]">Tenant</TableHead>
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
