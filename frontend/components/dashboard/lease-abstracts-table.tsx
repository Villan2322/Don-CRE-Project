'use client'

import { cn } from '@/lib/utils'
import { LeaseAbstract } from '@/lib/types'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { AlertCircle } from 'lucide-react'

interface LeaseAbstractsTableProps {
  abstracts: LeaseAbstract[]
}

export function LeaseAbstractsTable({ abstracts }: LeaseAbstractsTableProps) {
  const formatDate = (date: string | null) => {
    if (!date) return '—'
    return new Date(date).toLocaleDateString('en-US', {
      month: 'short',
      year: 'numeric',
    })
  }

  const expenseLabels = {
    NNN: 'NNN',
    GROSS: 'Gross',
    MODIFIED_GROSS: 'Mod. Gross',
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
              <TableHead className="w-[160px]">Tenant</TableHead>
              <TableHead>Suite</TableHead>
              <TableHead className="text-right">USF</TableHead>
              <TableHead className="text-right">RSF</TableHead>
              <TableHead className="text-right">LF</TableHead>
              <TableHead>Commencement</TableHead>
              <TableHead>Expiration</TableHead>
              <TableHead className="text-right">Base Rent</TableHead>
              <TableHead>Escalation</TableHead>
              <TableHead>Expense</TableHead>
              <TableHead>CAM Cap</TableHead>
              <TableHead>Gross-Up</TableHead>
              <TableHead>Fixed CAM</TableHead>
              <TableHead>Renewal</TableHead>
              <TableHead>Issues</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {abstracts.map((abstract) => (
              <TableRow key={abstract.id}>
                <TableCell className="font-medium">{abstract.tenantName}</TableCell>
                <TableCell className="text-muted-foreground">{abstract.suite}</TableCell>
                <TableCell className="text-right tabular-nums text-muted-foreground">
                  {abstract.usf ? abstract.usf.toLocaleString() : '—'}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {abstract.rsf.toLocaleString()}
                </TableCell>
                <TableCell className="text-right tabular-nums font-mono text-sm">
                  {abstract.loadFactor != null ? abstract.loadFactor.toFixed(4) : '—'}
                </TableCell>
                <TableCell className="tabular-nums">
                  {formatDate(abstract.commencementDate)}
                </TableCell>
                <TableCell
                  className={cn('tabular-nums', !abstract.expirationDate && 'text-destructive')}
                >
                  {abstract.expirationDate ? formatDate(abstract.expirationDate) : 'Missing'}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  ${abstract.baseRent.toLocaleString()}
                </TableCell>
                <TableCell
                  className={cn(
                    abstract.escalation === 'Unknown' && 'text-muted-foreground italic'
                  )}
                >
                  {abstract.escalation}
                </TableCell>
                <TableCell>
                  <Badge variant="secondary" className="text-xs">
                    {expenseLabels[abstract.expenseStructure]}
                  </Badge>
                </TableCell>
                <TableCell className="text-xs">
                  {abstract.camCap != null ? (
                    <span className="text-warning font-medium">{abstract.camCap}%</span>
                  ) : (
                    <span className="text-muted-foreground italic">None</span>
                  )}
                </TableCell>
                <TableCell className="text-xs">
                  {abstract.camGrossUp ? (
                    <span className="text-success font-medium">
                      Yes {abstract.grossUpThreshold != null ? `(${abstract.grossUpThreshold}%)` : ''}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">No</span>
                  )}
                </TableCell>
                <TableCell className="text-xs">
                  {abstract.fixedCAM ? (
                    <Badge variant="secondary" className="text-xs">Fixed</Badge>
                  ) : (
                    <span className="text-muted-foreground">Reconciling</span>
                  )}
                </TableCell>
                <TableCell className="text-sm">
                  {abstract.renewalOptions ? (
                    abstract.renewalOptions
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell>
                  {abstract.missingFields.length > 0 ? (
                    <div className="flex items-center gap-1.5 text-warning">
                      <AlertCircle className="h-3.5 w-3.5" />
                      <span className="text-xs">{abstract.missingFields.length} missing</span>
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
