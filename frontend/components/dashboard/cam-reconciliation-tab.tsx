'use client'

import { cn } from '@/lib/utils'
import { CAMReconciliation, TenantCAMRecord } from '@/lib/types'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { AlertTriangle, CheckCircle2, Info, TrendingDown, TrendingUp } from 'lucide-react'

interface CAMReconciliationTabProps {
  cam: CAMReconciliation
}

export function CAMReconciliationTab({ cam }: CAMReconciliationTabProps) {
  const fmt$ = (n: number) =>
    n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
  const fmtPct = (n: number) => `${n.toFixed(4)}`

  const totalOverUnder = cam.overUnderCollection
  const isOverCollected = totalOverUnder > 0
  const isUnderCollected = totalOverUnder < 0

  return (
    <div className="space-y-6">

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <SummaryCard
          label="Total Recoverable Expenses"
          value={fmt$(cam.totalRecoverableExpenses)}
          sub={`${cam.buildingTotalRSF.toLocaleString()} total building RSF`}
        />
        <SummaryCard
          label="CAM Billed to Tenants"
          value={fmt$(cam.totalBilled)}
          sub="Sum of all billed amounts"
        />
        <SummaryCard
          label="CAM Actually Owed"
          value={fmt$(cam.totalOwed)}
          sub="Per correct lease formula"
        />
        <SummaryCard
          label="Over / Under Collection"
          value={fmt$(Math.abs(totalOverUnder))}
          sub={isOverCollected ? 'Over-collected' : isUnderCollected ? 'Under-collected' : 'Balanced'}
          highlight={totalOverUnder !== 0}
          negative={isUnderCollected}
        />
      </div>

      {/* Load Factor Audit */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">Load Factor Audit</h3>
          <p className="text-xs text-muted-foreground">
            Reconciles implied load factor (RSF ÷ USF from rent roll) against load factor stated in each executed lease
          </p>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-[180px]">Tenant</TableHead>
                <TableHead>Suite</TableHead>
                <TableHead className="text-right">USF</TableHead>
                <TableHead className="text-right">RSF (Rent Roll)</TableHead>
                <TableHead className="text-right">Implied LF</TableHead>
                <TableHead className="text-right">Lease LF</TableHead>
                <TableHead className="text-right">Delta</TableHead>
                <TableHead className="text-right">Pro-Rata</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cam.tenantCAMSummary.map((tc) => {
                const hasLFDiscrepancy =
                  tc.leaseLoadFactor !== null &&
                  tc.loadFactorDelta !== null &&
                  Math.abs(tc.loadFactorDelta) > 0.005
                return (
                  <TableRow key={tc.tenantId}>
                    <TableCell className="font-medium">{tc.tenantName}</TableCell>
                    <TableCell className="text-muted-foreground">{tc.suite}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {tc.usf.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {tc.rsf.toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right tabular-nums font-mono text-sm">
                      {fmtPct(tc.loadFactor)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums font-mono text-sm">
                      {tc.leaseLoadFactor != null ? fmtPct(tc.leaseLoadFactor) : '—'}
                    </TableCell>
                    <TableCell
                      className={cn(
                        'text-right tabular-nums font-mono text-sm',
                        hasLFDiscrepancy ? 'text-destructive font-semibold' : 'text-muted-foreground'
                      )}
                    >
                      {tc.loadFactorDelta != null
                        ? `${tc.loadFactorDelta > 0 ? '+' : ''}${fmtPct(tc.loadFactorDelta)}`
                        : '—'}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {(tc.proRataShare * 100).toFixed(2)}%
                    </TableCell>
                    <TableCell>
                      {hasLFDiscrepancy ? (
                        <div className="flex items-center gap-1.5 text-destructive">
                          <AlertTriangle className="h-3.5 w-3.5" />
                          <span className="text-xs font-medium">Discrepancy</span>
                        </div>
                      ) : tc.leaseLoadFactor != null ? (
                        <div className="flex items-center gap-1.5 text-success">
                          <CheckCircle2 className="h-3.5 w-3.5" />
                          <span className="text-xs">Matched</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Info className="h-3.5 w-3.5" />
                          <span className="text-xs">No lease LF</span>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* CAM Calculation Per Tenant */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">CAM Calculation — Per Tenant</h3>
          <p className="text-xs text-muted-foreground">
            Correct formula applied per each lease&apos;s unique provisions
          </p>
        </div>
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-[160px]">Tenant</TableHead>
                <TableHead className="text-right">Pro-Rata</TableHead>
                <TableHead className="text-right">Total Recoverable</TableHead>
                <TableHead className="text-right">CAM Owed</TableHead>
                <TableHead className="text-right">CAM Billed</TableHead>
                <TableHead className="text-right">Over / Under</TableHead>
                <TableHead>Provisions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cam.tenantCAMSummary.map((tc) => {
                const diff = tc.overUnder
                return (
                  <TableRow key={tc.tenantId}>
                    <TableCell className="font-medium">{tc.tenantName}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {(tc.proRataShare * 100).toFixed(2)}%
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {fmt$(tc.totalRecoverableExpenses)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums font-medium">
                      {fmt$(tc.camOwed)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {tc.camBilled > 0 ? fmt$(tc.camBilled) : '—'}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {diff !== 0 ? (
                        <span
                          className={cn(
                            'flex items-center justify-end gap-1 font-medium',
                            diff > 0 ? 'text-warning' : 'text-destructive'
                          )}
                        >
                          {diff > 0 ? (
                            <TrendingUp className="h-3.5 w-3.5" />
                          ) : (
                            <TrendingDown className="h-3.5 w-3.5" />
                          )}
                          {fmt$(Math.abs(diff))}
                        </span>
                      ) : (
                        <span className="text-success text-sm">Balanced</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {tc.camCap != null && (
                          <ProvisionBadge label={`${tc.camCap}% cap`} applied={tc.camCapApplied} />
                        )}
                        {tc.grossUpApplied && <ProvisionBadge label="Gross-up" applied />}
                        {tc.fixedCAM && <ProvisionBadge label="Fixed CAM" applied={false} neutral />}
                        {tc.baseYear != null && (
                          <ProvisionBadge label={`Base yr ${tc.baseYear}`} applied={false} neutral />
                        )}
                        {tc.mgmtFeeCapPct != null && (
                          <ProvisionBadge label={`Mgmt ${tc.mgmtFeeCapPct}%`} applied={false} neutral />
                        )}
                        {tc.anchorExclusion && (
                          <ProvisionBadge label="Anchor excl." applied={false} neutral />
                        )}
                        {tc.expenseExclusions.length > 0 && (
                          <ProvisionBadge
                            label={`${tc.expenseExclusions.length} excl.`}
                            applied={false}
                            neutral
                          />
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Expense Categories */}
      {cam.expenseCategories.length > 0 && (
        <div className="rounded-lg border border-border bg-card">
          <div className="border-b border-border px-4 py-3">
            <h3 className="font-semibold">Expense Categories</h3>
            <p className="text-xs text-muted-foreground">
              GL-level breakdown of recoverable vs. excluded operating expenses
            </p>
          </div>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead>GL Code</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="text-right">Amount</TableHead>
                  <TableHead>Recoverable</TableHead>
                  <TableHead>Exclusion Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cam.expenseCategories.map((ec, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-sm">{ec.glCode || '—'}</TableCell>
                    <TableCell>{ec.description}</TableCell>
                    <TableCell className="text-right tabular-nums">{fmt$(ec.totalAmount)}</TableCell>
                    <TableCell>
                      {ec.recoverable ? (
                        <span className="text-xs text-success font-medium">Yes</span>
                      ) : (
                        <span className="text-xs text-destructive font-medium">Excluded</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {ec.exclusionReason ?? '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      {/* CAM Provision Reference */}
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">CAM Provision Reference</h3>
          <p className="text-xs text-muted-foreground">
            Key lease provisions extracted — what was applied and what was not
          </p>
        </div>
        <div className="divide-y divide-border">
          {cam.tenantCAMSummary.map((tc) => (
            <div key={tc.tenantId} className="px-4 py-4">
              <div className="mb-2 flex items-center gap-3">
                <span className="font-medium text-sm">{tc.tenantName}</span>
                <span className="text-xs text-muted-foreground">{tc.suite}</span>
                {tc.fixedCAM && (
                  <Badge variant="secondary" className="text-xs">Fixed CAM — No True-Up</Badge>
                )}
              </div>
              <div className="grid grid-cols-2 gap-x-8 gap-y-1.5 lg:grid-cols-4">
                <ProvisionRow label="CAM Cap" value={tc.camCap != null ? `${tc.camCap}% annual` : 'None'} flagMissing={tc.camCap == null} />
                <ProvisionRow label="Gross-Up Clause" value={tc.grossUpApplied ? 'Applied' : 'Not applicable'} />
                <ProvisionRow label="Mgmt Fee Cap" value={tc.mgmtFeeCapPct != null ? `${tc.mgmtFeeCapPct}%` : 'None stated'} flagMissing={tc.mgmtFeeCapPct == null} />
                <ProvisionRow label="Base Year Stop" value={tc.baseYear != null ? String(tc.baseYear) : 'None'} />
                <ProvisionRow label="Controllable Cap" value={tc.controllableCap != null ? `${tc.controllableCap}%` : 'None'} />
                <ProvisionRow label="Anchor Exclusion" value={tc.anchorExclusion ? 'Yes — excl. from denominator' : 'No'} />
                <ProvisionRow
                  label="Expense Exclusions"
                  value={tc.expenseExclusions.length > 0 ? tc.expenseExclusions.join(', ') : 'None stated'}
                  flagMissing={tc.expenseExclusions.length === 0}
                  wide
                />
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}

function SummaryCard({
  label,
  value,
  sub,
  highlight = false,
  negative = false,
}: {
  label: string
  value: string
  sub: string
  highlight?: boolean
  negative?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-lg border bg-card p-4',
        highlight
          ? negative
            ? 'border-destructive/40 bg-destructive/5'
            : 'border-warning/40 bg-warning/5'
          : 'border-border'
      )}
    >
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className={cn(
          'mt-1 text-xl font-semibold tabular-nums',
          highlight ? (negative ? 'text-destructive' : 'text-warning') : 'text-foreground'
        )}
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">{sub}</p>
    </div>
  )
}

function ProvisionBadge({
  label,
  applied,
  neutral = false,
}: {
  label: string
  applied: boolean
  neutral?: boolean
}) {
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-xs font-medium',
        neutral
          ? 'bg-secondary text-secondary-foreground'
          : applied
          ? 'bg-warning/20 text-warning'
          : 'bg-muted text-muted-foreground'
      )}
    >
      {label}
    </span>
  )
}

function ProvisionRow({
  label,
  value,
  flagMissing = false,
  wide = false,
}: {
  label: string
  value: string
  flagMissing?: boolean
  wide?: boolean
}) {
  return (
    <div className={cn('flex flex-col gap-0.5', wide && 'col-span-2')}>
      <span className="text-xs text-muted-foreground">{label}</span>
      <span
        className={cn(
          'text-xs font-medium',
          flagMissing ? 'text-warning italic' : 'text-foreground'
        )}
      >
        {value}
      </span>
    </div>
  )
}
