'use client'

import { cn } from '@/lib/utils'
import { UploadedDocument } from '@/lib/types'
import { FileText, CheckCircle2, Loader2, XCircle } from 'lucide-react'

interface DocumentsListProps {
  documents: UploadedDocument[]
}

export function DocumentsList({ documents }: DocumentsListProps) {
  const typeLabels: Record<UploadedDocument['type'], string> = {
    LEASE: 'Lease',
    RENT_ROLL: 'Rent Roll',
    BOMA: 'BOMA',
    MANAGEMENT_REPORT: 'Mgmt Report',
    COUNTY_PA: 'County PA',
    FINANCIAL_MODEL: 'Fin Model',
    LEASE_ABSTRACT: 'Lease Abstract',
    RENT_ROLL_XLSX: 'Rent Roll',
    CAM_RECONCILIATION: 'CAM Rec',
  }

  const statusConfig = {
    PROCESSED: { icon: CheckCircle2, color: 'text-success' },
    PROCESSING: { icon: Loader2, color: 'text-primary animate-spin' },
    FAILED: { icon: XCircle, color: 'text-destructive' },
  }

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Uploaded Documents</h3>
        <p className="text-xs text-muted-foreground">{documents.length} documents processed</p>
      </div>
      <ul className="divide-y divide-border">
        {documents.map((doc) => {
          const StatusIcon = statusConfig[doc.status].icon
          return (
            <li key={doc.id} className="flex items-center gap-3 p-3">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-secondary">
                <FileText className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{doc.filename}</p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span className="rounded bg-accent px-1.5 py-0.5">{typeLabels[doc.type]}</span>
                  <span>{doc.pageCount} pages</span>
                </div>
              </div>
              <StatusIcon className={cn('h-4 w-4', statusConfig[doc.status].color)} />
            </li>
          )
        })}
      </ul>
    </div>
  )
}
