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
import { ShieldCheck, ShieldAlert } from 'lucide-react'

interface TenantTableProps {
  tenants: Tenant[]
}

function ConfidenceBadge({ pct, coveStatus }: { pct?: number; coveStatus?: 'VERIFIED' | 'UNVERIFIED' }) {
  if (pct === undefined && coveStatus === undefined) return null

  const isVerified = coveStatus === 'VERIFIED' || (pct !== undefined && pct >= 90)
  const label      = pct !== undefined ? `${pct.toFixed(0)}%` : (isVerified ? 'VFD' : 'UNVFD')

  return (
    <span
      title={isVerified ? `COVE verified at ${pct?.toFixed(0) ?? ''}% confidence` : `Below 90% confidence threshold — numeric fields suppressed`}
      className={cn(
        'inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] font-medium tabular-nums',
        isVerified
          ? 'bg-emerald-500/15 text-emerald-400'
          : 'bg-amber-500/15 text-amber-400'
      )}
    >
      {isVerified
        ? <ShieldCheck className="h-2.5 w-2.5" />
        : <ShieldAlert className="h-2.5 w-2.5" />}
      {label}
    </span>
  )
}

export function TenantTable({ tenants }: TenantTableProps) {
  const hasCoveData = tenants.some(t => t.confidencePct !== undefined || t.coveStatus !== undefined)
  const unverifiedCount = tenants.filter(t => t.coveStatus === 'UNVERIFIED' || (t.confidencePct !== undefined && t.confidencePct < 90)).length

  const riskColors = {
    LOW:    'bg-success/20 text-success border-success/30',
    MEDIUM: 'bg-warning/20 text-warning border-warning/30',
    HIGH:   'bg-destructive/20 text-destructive border-destructive/30',
  }

  const arColors = {
    CURRENT:    'text-success',
    AT_RISK:    'text-warning',
    DELINQUENT: 'text-destructive',
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3 flex items-center justify-between gap-4">
        <div>
          <h3 className="font-semibold">Rent Roll</h3>
          <p className="text-xs text-muted-foreground">{tenants.length} tenants</p>
        </div>
        {hasCoveData && (
          <div className="flex items-center gap-3 text-xs">
            <span className="flex items-center gap-1 text-emerald-400">
              <ShieldCheck className="h-3.5 w-3.5" />
              {tenants.length - unverifiedCount} verified
            </span>
            {unverifiedCount > 0 && (
              <span className="flex items-center gap-1 text-amber-400">
                <ShieldAlert className="h-3.5 w-3.5" />
                {unverifiedCount} need verification
              </span>
            )}
            <span className="text-muted-foreground">COVE threshold: 90%</span>
          </div>
        )}
      </div>
      {unverifiedCount > 0 && (
        <div className="border-b border-border bg-amber-500/5 px-4 py-2 flex items-center gap-2">
          <ShieldAlert className="h-3.5 w-3.5 shrink-0 text-amber-400" />
          <p className="text-xs text-amber-400">
            {unverifiedCount} tenant row{unverifiedCount !== 1 ? 's' : ''} below 90% confidence — RSF and/or rent fields are suppressed and shown as &ldquo;—&rdquo; until manually verified
          </p>
        </div>
      )}
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="w-[180px]">Tenant</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead className="text-right">RSF</TableHead>
              <TableHead className="text-right">BOMA RSF</TableHead>
              <TableHead className="text-right">Delta</TableHead>
              <TableHead className="text-right">Rent/SF</TableHead>
              <TableHead className="text-right">Annual</TableHead>
              <TableHead className="text-right">Exp</TableHead>
              <TableHead className="text-right">Income %</TableHead>
              <TableHead>AR</TableHead>
              <TableHead>Risk</TableHead>
              {hasCoveData && <TableHead className="text-right">Confidence</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {tenants.map((tenant) => {
              const isUnverified = tenant.coveStatus === 'UNVERIFIED' ||
                (tenant.confidencePct !== undefined && tenant.confidencePct < 90)
              return (
                <TableRow
                  key={tenant.id}
                  className={cn(isUnverified && 'opacity-70 bg-amber-500/5')}
                >
                  <TableCell className="font-medium">{tenant.name}</TableCell>
                  <TableCell className="text-muted-foreground">{tenant.suite}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {tenant.rsf != null ? tenant.rsf.toLocaleString() : <span className="text-muted-foreground">—</span>}
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
                    {tenant.rentPSF != null ? `$${tenant.rentPSF.toFixed(2)}` : <span className="text-muted-foreground">—</span>}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {tenant.annualRent != null ? `$${tenant.annualRent.toLocaleString()}` : <span className="text-muted-foreground">—</span>}
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
                  {hasCoveData && (
                    <TableCell className="text-right">
                      <ConfidenceBadge pct={tenant.confidencePct} coveStatus={tenant.coveStatus} />
                    </TableCell>
                  )}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
