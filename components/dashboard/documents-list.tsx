'use client'

import { cn } from '@/lib/utils'
import { DocumentType, UploadedDocument } from '@/lib/types'
import { FileText, CheckCircle2, MinusCircle, XCircle } from 'lucide-react'

const TYPE_LABELS: Record<DocumentType, string> = {
  LEASE: 'Lease',
  LEASE_ABSTRACT: 'Lease Abstract',
  RENT_ROLL: 'Rent Roll',
  BOMA: 'BOMA',
  MANAGEMENT_REPORT: 'Mgmt Report',
  COUNTY_PA: 'County PA',
  FINANCIAL_MODEL: 'Fin Model',
  CAM_RECONCILIATION: 'CAM Rec',
  OTHER: 'Other',
}

const STATUS = {
  PROCESSED: { icon: CheckCircle2, color: 'text-success', label: 'Extracted' },
  SKIPPED: { icon: MinusCircle, color: 'text-muted-foreground', label: 'Skipped' },
  FAILED: { icon: XCircle, color: 'text-destructive', label: 'Failed' },
}

export function DocumentsList({ documents }: { documents: UploadedDocument[] }) {
  const processed = documents.filter((d) => d.status === 'PROCESSED').length
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Documents</h3>
        <p className="text-xs text-muted-foreground">
          {processed} of {documents.length} extracted
        </p>
      </div>
      <ul className="divide-y divide-border">
        {documents.map((doc) => {
          const s = STATUS[doc.status]
          const Icon = s.icon
          return (
            <li key={doc.id} className="flex items-start gap-3 p-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded bg-secondary">
                <FileText className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium" title={doc.filename}>
                  {doc.filename}
                </p>
                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <span className="rounded bg-accent px-1.5 py-0.5">{TYPE_LABELS[doc.type] ?? doc.type}</span>
                  {doc.pageCount > 0 && <span>{doc.pageCount} page{doc.pageCount !== 1 && 's'}</span>}
                  {doc.ocr && <span>OCR</span>}
                </div>
                {doc.note && <p className={cn('mt-1 text-xs', doc.status === 'FAILED' ? 'text-destructive' : 'text-muted-foreground')}>{doc.note}</p>}
              </div>
              <Icon className={cn('h-4 w-4 shrink-0', s.color)} aria-label={s.label} />
            </li>
          )
        })}
      </ul>
    </div>
  )
}
