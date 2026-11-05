'use client'

import { cn } from '@/lib/utils'
import { money, monthYear, sf } from '@/lib/format'
import { LeaseAbstract } from '@/lib/types'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { AlertCircle } from 'lucide-react'

const EXPENSE = { NNN: 'NNN', GROSS: 'Gross', MODIFIED_GROSS: 'Mod. Gross' }
const FIELD_NAMES: Record<string, string> = {
  tenant_name: 'tenant name',
  rentable_sf: 'rentable SF',
  lease_expiration_date: 'expiration date',
  base_rent_annual: 'annual rent',
}

export function LeaseAbstractsTable({ abstracts }: { abstracts: LeaseAbstract[] }) {
  if (abstracts.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
        No leases or lease abstracts in this package.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Lease Abstracts</h3>
        <p className="text-xs text-muted-foreground">{abstracts.length} leases abstracted</p>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead className="min-w-[180px]">Tenant</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead className="text-right">RSF</TableHead>
              <TableHead>Commencement</TableHead>
              <TableHead>Expiration</TableHead>
              <TableHead className="text-right">Base Rent</TableHead>
              <TableHead>Escalation</TableHead>
              <TableHead>Expense</TableHead>
              <TableHead className="min-w-[200px]">Renewal</TableHead>
              <TableHead>Issues</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {abstracts.map((a) => (
              <TableRow key={a.id}>
                <TableCell className="font-medium">
                  {a.tenantName}
                  <div className="truncate text-xs font-normal text-muted-foreground" title={a.sourceFile}>
                    {a.sourceFile}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{a.suite || '—'}</TableCell>
                <TableCell className="text-right tabular-nums">{sf(a.rsf || null)}</TableCell>
                <TableCell className="tabular-nums">{monthYear(a.commencementDate)}</TableCell>
                <TableCell className={cn('tabular-nums', !a.expirationDate && 'text-destructive')}>
                  {a.expirationDate ? monthYear(a.expirationDate) : 'Missing'}
                </TableCell>
                <TableCell className="text-right tabular-nums">{a.baseRent ? money(a.baseRent) : '—'}</TableCell>
                <TableCell className={cn(a.escalation === 'Unknown' && 'italic text-muted-foreground')}>
                  {a.escalation}
                </TableCell>
                <TableCell>
                  {a.expenseStructure ? (
                    <Badge variant="secondary" className="text-xs" title={a.expenseStructureText ?? undefined}>
                      {EXPENSE[a.expenseStructure]}
                    </Badge>
                  ) : (
                    <span className="text-muted-foreground">{a.expenseStructureText ?? '—'}</span>
                  )}
                </TableCell>
                <TableCell className="text-sm">
                  {a.renewalOptions ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell>
                  {a.missingFields.length > 0 ? (
                    <div
                      className="flex items-center gap-1.5 text-warning"
                      title={`Missing: ${a.missingFields.map((f) => FIELD_NAMES[f] ?? f).join(', ')}`}
                    >
                      <AlertCircle className="h-3.5 w-3.5" />
                      <span className="text-xs">{a.missingFields.length} missing</span>
                    </div>
                  ) : (
                    <span className="text-xs text-success">Complete</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
