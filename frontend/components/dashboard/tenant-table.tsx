'use client'

import { cn } from '@/lib/utils'
import { Tenant } from '@/lib/types'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'

interface TenantTableProps {
  tenants: Tenant[]
}

export function TenantTable({ tenants }: TenantTableProps) {
  const riskColors = {
    LOW: 'bg-success/20 text-success border-success/30',
    MEDIUM: 'bg-warning/20 text-warning border-warning/30',
    HIGH: 'bg-destructive/20 text-destructive border-destructive/30',
  }

  const arColors = {
    CURRENT: 'text-success',
    AT_RISK: 'text-warning',
    DELINQUENT: 'text-destructive',
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Rent Roll</h3>
        <p className="text-xs text-muted-foreground">{tenants.length} tenants</p>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[160px]">Tenant</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead className="text-right">USF</TableHead>
              <TableHead className="text-right">RSF</TableHead>
              <TableHead className="text-right">LF (Implied)</TableHead>
              <TableHead className="text-right">LF (Lease)</TableHead>
              <TableHead className="text-right">Pro-Rata %</TableHead>
              <TableHead className="text-right">BOMA RSF</TableHead>
              <TableHead className="text-right">Delta</TableHead>
              <TableHead className="text-right">Rent/SF</TableHead>
              <TableHead className="text-right">Annual</TableHead>
              <TableHead className="text-right">Exp</TableHead>
              <TableHead className="text-right">Income %</TableHead>
              <TableHead>AR</TableHead>
              <TableHead>Risk</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tenants.map((tenant) => (
              <TableRow key={tenant.id}>
                <TableCell className="font-medium">{tenant.name}</TableCell>
                <TableCell className="text-muted-foreground">{tenant.suite}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {tenant.usf ? Math.round(tenant.usf).toLocaleString() : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {tenant.rsf.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums font-mono text-sm">
                  {tenant.loadFactor != null ? tenant.loadFactor.toFixed(4) : '—'}
                </TableCell>
                <TableCell className={cn(
                  'text-right tabular-nums font-mono text-sm',
                  tenant.leaseLoadFactor != null && tenant.loadFactor != null &&
                  Math.abs(tenant.leaseLoadFactor - tenant.loadFactor) > 0.01
                    ? 'text-warning'
                    : ''
                )}>
                  {tenant.leaseLoadFactor != null ? tenant.leaseLoadFactor.toFixed(4) : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums text-sm">
                  {tenant.proRataShare != null ? `${(tenant.proRataShare * 100).toFixed(2)}%` : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {tenant.bomaRsf?.toLocaleString() ?? '—'}
                </TableCell>
                <TableCell
                  className={cn(
                    'text-right tabular-nums',
                    tenant.rsfDelta && tenant.rsfDelta > 0 ? 'text-warning' : ''
                  )}
                >
                  {tenant.rsfDelta ? `+${tenant.rsfDelta.toLocaleString()}` : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  ${tenant.rentPSF.toFixed(2)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  ${tenant.annualRent.toLocaleString()}
                </TableCell>
                <TableCell className="text-right">
                  {tenant.leaseExpiry ? (
                    <span
                      className={cn(
                        'tabular-nums',
                        tenant.monthsRemaining && tenant.monthsRemaining <= 12 ? 'text-warning' : ''
                      )}
                    >
                      {tenant.monthsRemaining}mo
                    </span>
                  ) : (
                    <span className="text-destructive">N/A</span>
                  )}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {tenant.incomeConcentration}%
                </TableCell>
                <TableCell>
                  <span className={cn('text-sm', arColors[tenant.arStatus])}>
                    {tenant.arStatus === 'DELINQUENT'
                      ? `$${tenant.arBalance.toLocaleString()}`
                      : tenant.arStatus === 'CURRENT'
                        ? 'Current'
                        : 'At Risk'}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge variant="outline" className={cn('text-xs', riskColors[tenant.riskLevel])}>
                    {tenant.riskLevel}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
