'use client'

import { AlertCircle, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { scoreHistory } from '@/lib/deal-history'
import { money, monthYear, sf, term } from '@/lib/format'
import { ArithmeticCheck, DealAnalysis, TabId, UploadMode } from '@/lib/types'
import { canAddDocuments } from '@/lib/carry'
import { ScoreCard } from './score-card'
import { RSFAlert } from './rsf-alert'
import { MetricsGrid } from './metrics-grid'
import { RedFlagsList } from './red-flags-list'
import { WhatToGetNext } from './what-to-get-next'
import { ScoreHistoryChart, IncomeConcentrationChart, ExpiryScheduleChart } from './charts'
import { TenantTable } from './tenant-table'
import { LeaseAbstractsTable } from './lease-abstracts-table'
import { DocumentsList } from './documents-list'
import { DocumentUpload } from './document-upload'
import { MobileTabs } from './sidebar'
import { AreaAudit } from './area-audit'

interface TabContentProps {
  activeTab: TabId
  deal: DealAnalysis
  history: DealAnalysis[]
  onAnalysisComplete: (analysis: DealAnalysis) => void
  onTabChange: (tab: TabId) => void
  uploadMode: UploadMode
  onUploadModeChange: (mode: UploadMode) => void
  onAddDocuments: () => void
}

export function TabContent({
  activeTab, deal, history, onAnalysisComplete, onTabChange, uploadMode, onUploadModeChange, onAddDocuments,
}: TabContentProps) {
  const onAdd = canAddDocuments(deal) ? onAddDocuments : undefined
  const body = (() => {
    switch (activeTab) {
      case 'audit':
        return <AuditTab deal={deal} onAdd={onAdd} />
      case 'rent-roll':
        return <RentRollTab deal={deal} />
      case 'lease-audit':
        return <AreaAudit deal={deal} onUpload={() => onTabChange('upload')} />
      case 'expirations':
        return <ExpirationsTab deal={deal} />
      case 'risk':
        return <RiskTab deal={deal} />
      case 'abstracts':
        return <AbstractsTab deal={deal} />
      case 'upload':
        return (
          <DocumentUpload
            key={`${deal.id}:${uploadMode}`}
            onAnalysisComplete={onAnalysisComplete}
            baseDeal={deal}
            mode={uploadMode}
            onModeChange={onUploadModeChange}
          />
        )
      default:
        return <SnapshotTab deal={deal} history={history} onAdd={onAdd} />
    }
  })()

  return (
    <div className="mx-auto max-w-7xl">
      <MobileTabs activeTab={activeTab} onTabChange={onTabChange} />
      {activeTab !== 'upload' && <Notices deal={deal} onUpload={() => onTabChange('upload')} />}
      {body}
    </div>
  )
}

function Notices({ deal, onUpload }: { deal: DealAnalysis; onUpload: () => void }) {
  if (deal.isSample) {
    return (
      <div className="mb-6 flex flex-wrap items-center gap-3 rounded-lg border border-primary/15 bg-accent px-4 py-3 text-sm">
        <Info className="h-4 w-4 shrink-0 text-brand-navy" />
        <span className="min-w-0 flex-1 basis-56">
          Sample analysis of a test package — tenant rents other than Bank of America are illustrative.
        </span>
        <button className="-my-2 py-2.5 font-medium text-primary hover:underline" onClick={onUpload}>
          Analyze your own deal
        </button>
      </div>
    )
  }
  if (deal.pipelineErrors.length === 0) return null
  return (
    <div className="mb-6 rounded-lg border border-destructive/30 bg-destructive-soft px-4 py-3 text-sm">
      <div className="flex items-center gap-2 font-medium text-destructive">
        <AlertCircle className="h-4 w-4" />
        Some steps had problems — results below cover what could be read
      </div>
      <ul className="mt-1 list-disc space-y-0.5 pl-10 text-xs text-muted-foreground">
        {deal.pipelineErrors.slice(0, 5).map((e, i) => (
          <li key={i}>{e}</li>
        ))}
      </ul>
    </div>
  )
}

function SectionHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div>
      <h2 className="text-2xl md:text-[28px]">{title}</h2>
      <div className="mt-2 h-[3px] w-12 bg-gold" />
      <p className="mt-3 text-sm text-muted-foreground">{subtitle}</p>
    </div>
  )
}

function SnapshotTab({ deal, history, onAdd }: { deal: DealAnalysis; history: DealAnalysis[]; onAdd?: () => void }) {
  return (
    <div className="space-y-6">
      <ScoreCard deal={deal} />
      <RSFAlert rsf={deal.rsfReconciliation} />
      <MetricsGrid deal={deal} />
      <div className="grid gap-6 lg:grid-cols-3">
        <ScoreHistoryChart points={scoreHistory(deal, history)} />
        <IncomeConcentrationChart tenants={deal.tenants} />
        <ExpiryScheduleChart schedule={deal.expirySchedule} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <RedFlagsList flags={deal.redFlags} limit={4} />
        <WhatToGetNext items={deal.whatToGetNext} onAdd={onAdd} />
      </div>
    </div>
  )
}

function AuditTab({ deal, onAdd }: { deal: DealAnalysis; onAdd?: () => void }) {
  return (
    <div className="space-y-6">
      <SectionHeader title="Audit Log" subtitle="Every flag, every arithmetic check, and every document read" />
      <RedFlagsList flags={deal.redFlags} />
      <div className="grid gap-6 lg:grid-cols-2">
        <DocumentsList documents={deal.documents} onAdd={onAdd} />
        <ArithmeticChecks checks={deal.arithmeticChecks} />
      </div>
    </div>
  )
}

const CHECK_STYLE = {
  pass: { color: 'text-success', label: 'Verified' },
  warning: { color: 'text-warning', label: 'Warning' },
  fail: { color: 'text-destructive', label: 'Mismatch' },
}

function ArithmeticChecks({ checks }: { checks: ArithmeticCheck[] }) {
  const ordered = [...checks].sort(
    (a, b) => ['fail', 'warning', 'pass'].indexOf(a.status) - ['fail', 'warning', 'pass'].indexOf(b.status)
  )
  const passed = checks.filter((c) => c.status === 'pass').length
  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="border-b border-border px-4 py-3">
        <h3 className="font-semibold">Arithmetic Checks</h3>
        <p className="text-xs text-muted-foreground">
          Totals stated in the documents, recomputed from their line items · {passed} of {checks.length} verified
        </p>
      </div>
      {checks.length === 0 ? (
        <p className="p-4 text-sm text-muted-foreground">No stated totals in these documents to verify.</p>
      ) : (
        <ul className="divide-y divide-border">
          {ordered.map((c, i) => (
            <li key={i} className="flex items-start justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="text-sm">{c.label}</p>
                <p className="text-xs text-muted-foreground">
                  {c.detail ?? c.formula} · {c.source}
                </p>
              </div>
              <span className={cn('shrink-0 text-sm font-medium', CHECK_STYLE[c.status].color)}>
                {CHECK_STYLE[c.status].label}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function RentRollTab({ deal }: { deal: DealAnalysis }) {
  const fin = deal.financialSummary
  const rsf = deal.rsfReconciliation
  return (
    <div className="space-y-6">
      <SectionHeader title="Rent Roll + Revenue Engine" subtitle="Per-tenant rent, RSF against BOMA, expirations, and collections" />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Total annual rent" value={money(fin.totalAnnualRent)} />
        <StatCard label="Avg rent / SF" value={fin.averageRentPSF ? money(fin.averageRentPSF, 2) : '—'} />
        <StatCard label="Billed SF" value={sf(rsf.rentRollOccupiedSF)} />
        <StatCard
          label="Potential recovery"
          value={rsf.estimatedAnnualRecovery ? money(rsf.estimatedAnnualRecovery) : '—'}
          highlight={rsf.estimatedAnnualRecovery > 0}
        />
      </div>
      <TenantTable tenants={deal.tenants} />
    </div>
  )
}

function ExpirationsTab({ deal }: { deal: DealAnalysis }) {
  const atRisk = deal.tenants.filter((t) => t.monthsRemaining === null || t.monthsRemaining <= 12)
  const schedule = [...deal.tenants].sort(
    (a, b) => (a.monthsRemaining ?? Number.MAX_SAFE_INTEGER) - (b.monthsRemaining ?? Number.MAX_SAFE_INTEGER)
  )

  return (
    <div className="space-y-6">
      <SectionHeader title="Lease Expirations" subtitle="Expiration schedule, WALT, and income at risk" />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="WALT"
          value={deal.walt === null ? '—' : `${Math.round(deal.walt)} months`}
          sub={`${Math.round(deal.waltCoverage)}% of rent has a known expiry`}
        />
        <StatCard label="Expired, undated, or ≤ 12 months" value={atRisk.length.toString()} />
        <StatCard
          label="Income at risk"
          value={money(atRisk.reduce((sum, t) => sum + t.annualRent, 0))}
          highlight={atRisk.length > 0}
        />
      </div>
      <ExpiryScheduleChart schedule={deal.expirySchedule} />
      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">Expiration order</h3>
        </div>
        <div className="divide-y divide-border">
          {schedule.map((t) => {
            const unknown = t.monthsRemaining === null
            const expired = !unknown && (t.monthsRemaining as number) < 0
            const near = !unknown && (t.monthsRemaining as number) <= 12
            return (
              <div key={t.id} className={cn('flex items-center justify-between gap-4 p-4', unknown && 'bg-destructive-soft')}>
                <div className="min-w-0">
                  <p className="truncate font-medium">{t.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {t.suite || 'Suite not listed'} · {t.incomeConcentration}% of rent
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p
                    className={cn(
                      'font-medium tabular-nums',
                      (unknown || expired) && 'text-destructive',
                      near && !expired && 'text-warning'
                    )}
                  >
                    {unknown ? (t.monthToMonth ? 'Month-to-month' : 'Expiry unknown') : `${monthYear(t.leaseExpiry)} · ${term(t.monthsRemaining)}`}
                  </p>
                  <p className="text-xs text-muted-foreground">{money(t.annualRent)}/yr</p>
                </div>
              </div>
            )
          })}
          {schedule.length === 0 && <p className="p-4 text-sm text-muted-foreground">No tenants in this package.</p>}
        </div>
      </div>
    </div>
  )
}

function RiskTab({ deal }: { deal: DealAnalysis }) {
  return (
    <div className="space-y-6">
      <SectionHeader title="Risk Dashboard" subtitle="How the score was built — every point earned or missed" />
      <ScoreCard deal={deal} detailed />
      <RSFAlert rsf={deal.rsfReconciliation} />
      <div className="grid gap-6 lg:grid-cols-2">
        <RedFlagsList flags={deal.redFlags} />
        <WhatToGetNext items={deal.whatToGetNext} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <IncomeConcentrationChart tenants={deal.tenants} />
        <ExpiryScheduleChart schedule={deal.expirySchedule} />
      </div>
    </div>
  )
}

function AbstractsTab({ deal }: { deal: DealAnalysis }) {
  const incomplete = deal.leaseAbstracts.filter((a) => a.missingFields.length > 0).length
  return (
    <div className="space-y-6">
      <SectionHeader title="Lease Abstracts" subtitle="Key terms extracted from each lease and amendment" />
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label="Leases abstracted" value={deal.leaseAbstracts.length.toString()} />
        <StatCard label="Complete" value={(deal.leaseAbstracts.length - incomplete).toString()} />
        <StatCard label="Missing key fields" value={incomplete.toString()} highlight={incomplete > 0} />
      </div>
      <LeaseAbstractsTable abstracts={deal.leaseAbstracts} />
    </div>
  )
}

function StatCard({ label, value, sub, highlight = false }: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="eyebrow">{label}</div>
      <div className={cn('mt-2 text-2xl font-semibold tabular-nums text-brand-navy', highlight && 'text-warning')}>{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}
