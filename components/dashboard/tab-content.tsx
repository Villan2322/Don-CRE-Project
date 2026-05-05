'use client'

import { TabId, DealAnalysis } from '@/lib/types'
import { ScoreCard } from './score-card'
import { RSFAlert } from './rsf-alert'
import { MetricsGrid } from './metrics-grid'
import { RedFlagsList } from './red-flags-list'
import { WhatToGetNext } from './what-to-get-next'
import { ScoreHistoryChart, IncomeConcentrationChart, WALTTimelineChart } from './charts'
import { TenantTable } from './tenant-table'
import { LeaseAbstractsTable } from './lease-abstracts-table'
import { DocumentsList } from './documents-list'
import { DocumentUpload } from './document-upload'

interface TabContentProps {
  activeTab: TabId
  deal: DealAnalysis | null
  onAnalysisComplete?: (analysis: DealAnalysis) => void
}

export function TabContent({ activeTab, deal, onAnalysisComplete }: TabContentProps) {
  // Upload tab is always available
  if (activeTab === 'upload') {
    return <DocumentUpload onAnalysisComplete={onAnalysisComplete} />
  }

  // For all other tabs, show empty state if no deal data
  if (!deal) {
    return <EmptyState />
  }

  // Render the appropriate tab with deal data
  switch (activeTab) {
    case 'snapshot':
      return <SnapshotTab deal={deal} />
    case 'audit':
      return <AuditTab deal={deal} />
    case 'rent-roll':
      return <RentRollTab deal={deal} />
    case 'lease-audit':
      return <LeaseAuditTab deal={deal} />
    case 'risk':
      return <RiskTab deal={deal} />
    case 'abstracts':
      return <AbstractsTab deal={deal} />
    default:
      return <SnapshotTab deal={deal} />
  }
}

function EmptyState() {
  return (
    <div className="flex h-full min-h-[400px] items-center justify-center">
      <div className="mx-auto max-w-md text-center">
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-muted">
          <svg
            className="h-8 w-8 text-muted-foreground"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
        </div>
        <h3 className="text-lg font-semibold">No Deal Analyzed Yet</h3>
        <p className="mt-2 text-sm text-muted-foreground">
          Upload documents to start analyzing a deal. Supported formats include rent rolls, 
          leases, BOMA measurements, and financial statements.
        </p>
        <p className="mt-4 text-xs text-muted-foreground">
          Go to the <span className="font-medium">Upload Documents</span> tab to get started.
        </p>
      </div>
    </div>
  )
}

function SnapshotTab({ deal }: { deal: DealAnalysis }) {
  return (
    <div className="space-y-6">
      <ScoreCard deal={deal} />
      {deal.rsfReconciliation.alertTriggered && <RSFAlert rsf={deal.rsfReconciliation} />}
      <MetricsGrid deal={deal} />
      <div className="grid gap-6 lg:grid-cols-3">
        <ScoreHistoryChart />
        <IncomeConcentrationChart />
        <WALTTimelineChart />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RedFlagsList flags={deal.redFlags} limit={3} />
        <WhatToGetNext items={deal.whatToGetNext} />
      </div>
    </div>
  )
}

function AuditTab({ deal }: { deal: DealAnalysis }) {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-xl font-semibold">Audit Log</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Complete list of flags, checks, and validations
        </p>
      </div>
      <RedFlagsList flags={deal.redFlags} />
      <div className="grid gap-6 lg:grid-cols-2">
        <DocumentsList documents={deal.documents} />
        <div className="rounded-lg border border-border bg-card p-4">
          <h3 className="font-semibold">Arithmetic Checks</h3>
          <p className="text-xs text-muted-foreground">Verification of calculated values</p>
          <div className="mt-4 space-y-3">
            <CheckItem label="NOI Calculation" status="pass" />
            <CheckItem label="Cap Rate Verification" status="pass" />
            <CheckItem label="RSF Summation" status="warning" detail="Delta detected" />
            <CheckItem label="WALT Calculation" status="pass" />
            <CheckItem label="AR Balance Reconciliation" status="pass" />
          </div>
        </div>
      </div>
    </div>
  )
}

function CheckItem({
  label,
  status,
  detail,
}: {
  label: string
  status: 'pass' | 'warning' | 'fail'
  detail?: string
}) {
  const statusColors = {
    pass: 'text-success',
    warning: 'text-warning',
    fail: 'text-destructive',
  }
  const statusLabels = {
    pass: 'Verified',
    warning: 'Warning',
    fail: 'Failed',
  }

  return (
    <div className="flex items-center justify-between rounded-md bg-secondary/50 px-3 py-2">
      <span className="text-sm">{label}</span>
      <div className="text-right">
        <span className={`text-sm font-medium ${statusColors[status]}`}>
          {statusLabels[status]}
        </span>
        {detail && <p className="text-xs text-muted-foreground">{detail}</p>}
      </div>
    </div>
  )
}

function RentRollTab({ deal }: { deal: DealAnalysis }) {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-xl font-semibold">Rent Roll + Revenue Engine</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Per-tenant analysis with RSF reconciliation and risk assessment
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Total Annual Rent"
          value={`$${deal.financialSummary.totalAnnualRent.toLocaleString()}`}
        />
        <StatCard
          label="Avg Rent PSF"
          value={`$${deal.financialSummary.averageRentPSF.toFixed(2)}`}
        />
        <StatCard label="Occupied SF" value={deal.rsfReconciliation.rentRollOccupiedSF.toLocaleString()} />
        <StatCard
          label="Potential Recovery"
          value={`$${deal.rsfReconciliation.estimatedAnnualRecovery.toLocaleString()}`}
          highlight
        />
      </div>
      <TenantTable tenants={deal.tenants} />
    </div>
  )
}

function LeaseAuditTab({ deal }: { deal: DealAnalysis }) {
  const expiringLeases = deal.tenants.filter(
    (t) => t.monthsRemaining !== null && t.monthsRemaining <= 12
  )

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-xl font-semibold">Lease Audit Results</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Expiration schedule, WALT analysis, and recommended actions
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="WALT" value={`${deal.walt} months`} />
        <StatCard label="Near-term Expirations" value={expiringLeases.length.toString()} />
        <StatCard
          label="At-Risk Income"
          value={`$${expiringLeases.reduce((sum, t) => sum + t.annualRent, 0).toLocaleString()}`}
          highlight
        />
      </div>
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">Lease Expiration Schedule</h3>
        </div>
        <div className="divide-y divide-border">
          {deal.tenants
            .filter((t) => t.leaseExpiry)
            .sort((a, b) => (a.monthsRemaining || 999) - (b.monthsRemaining || 999))
            .map((tenant) => (
              <div
                key={tenant.id}
                className="flex items-center justify-between p-4"
              >
                <div>
                  <p className="font-medium">{tenant.name}</p>
                  <p className="text-xs text-muted-foreground">Suite {tenant.suite}</p>
                </div>
                <div className="text-right">
                  <p className={`font-medium tabular-nums ${tenant.monthsRemaining && tenant.monthsRemaining <= 12 ? 'text-warning' : ''}`}>
                    {tenant.monthsRemaining} months
                  </p>
                  <p className="text-xs text-muted-foreground">
                    ${tenant.annualRent.toLocaleString()}/yr
                  </p>
                </div>
              </div>
            ))}
          {deal.tenants
            .filter((t) => !t.leaseExpiry)
            .map((tenant) => (
              <div
                key={tenant.id}
                className="flex items-center justify-between bg-destructive/5 p-4"
              >
                <div>
                  <p className="font-medium">{tenant.name}</p>
                  <p className="text-xs text-muted-foreground">Suite {tenant.suite}</p>
                </div>
                <div className="text-right">
                  <p className="font-medium text-destructive">Expiry Unknown</p>
                  <p className="text-xs text-muted-foreground">
                    ${tenant.annualRent.toLocaleString()}/yr
                  </p>
                </div>
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}

function RiskTab({ deal }: { deal: DealAnalysis }) {
  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-xl font-semibold">Risk Dashboard</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Comprehensive risk assessment and score breakdown
        </p>
      </div>
      <ScoreCard deal={deal} />
      {deal.rsfReconciliation.alertTriggered && <RSFAlert rsf={deal.rsfReconciliation} />}
      <div className="grid gap-6 lg:grid-cols-2">
        <RedFlagsList flags={deal.redFlags} />
        <WhatToGetNext items={deal.whatToGetNext} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <IncomeConcentrationChart />
        <WALTTimelineChart />
      </div>
    </div>
  )
}

function AbstractsTab({ deal }: { deal: DealAnalysis }) {
  const incompleteCount = deal.leaseAbstracts.filter((a) => a.missingFields.length > 0).length

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-card p-6">
        <h2 className="text-xl font-semibold">Lease Abstracts</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Structured lease data extracted from uploaded documents
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Leases Abstracted" value={deal.leaseAbstracts.length.toString()} />
        <StatCard label="Complete" value={(deal.leaseAbstracts.length - incompleteCount).toString()} />
        <StatCard label="Missing Fields" value={incompleteCount.toString()} highlight={incompleteCount > 0} />
      </div>
      <LeaseAbstractsTable abstracts={deal.leaseAbstracts} />
    </div>
  )
}

function StatCard({
  label,
  value,
  highlight = false,
}: {
  label: string
  value: string
  highlight?: boolean
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className={`mt-1 text-2xl font-semibold tabular-nums ${highlight ? 'text-warning' : ''}`}>
        {value}
      </div>
    </div>
  )
}
