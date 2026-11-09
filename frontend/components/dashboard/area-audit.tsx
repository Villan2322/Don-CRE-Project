'use client'

import { Fragment, useState } from 'react'
import { ChevronDown, ChevronRight, Ruler } from 'lucide-react'
import { cn } from '@/lib/utils'
import { money, sf } from '@/lib/format'
import { DealAnalysis, LeaseAuditRow, LeverageCall } from '@/lib/types'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const LEVERAGE: Record<LeverageCall, { label: string; style: string }> = {
  STRONG: { label: 'Can remeasure', style: 'bg-success-soft text-success border-success/30' },
  NEGOTIABLE: { label: 'Negotiable', style: 'bg-warning-soft text-warning border-warning/30' },
  NONE: { label: 'Locked', style: 'bg-muted text-muted-foreground border-border' },
  NO_LEASE: { label: 'Need lease', style: 'bg-primary/10 text-primary border-primary/30' },
  OVERBILLED: { label: 'Overbilled', style: 'bg-destructive-soft text-destructive border-destructive/30' },
  MATCHES: { label: 'Matches', style: 'bg-muted text-muted-foreground border-border' },
}

const TERM_LABELS: Record<string, string> = {
  expense_structure_text: 'Expense structure',
  recoverable: 'Tenant pays a share of',
  exclusions: 'Excluded expenses',
  cam_cap: 'CAM cap',
  admin_fee: 'Admin / management fee',
  gross_up: 'Gross-up',
  base_year: 'Base year / stop',
  lease_share: 'Share stated in lease (%)',
  lease_share_basis: 'How the share is defined',
}

export function AreaAudit({ deal, onUpload }: { deal: DealAnalysis; onUpload: () => void }) {
  const audit = deal.leaseAudit
  const [open, setOpen] = useState<string | null>(null)

  const header = (
    <div className="mb-6">
      <h2 className="text-2xl md:text-[28px]">Lease Audit</h2>
      <div className="mt-2 h-[3px] w-12 bg-gold" />
      <p className="mt-3 text-sm text-muted-foreground">
        Is each tenant paying for the space it occupies? Billed area vs the BOMA measurement, in rent and CAM.
      </p>
    </div>
  )

  if (!audit || !audit.available) {
    return (
      <div>
        {header}
        <div className="rounded-lg border border-border bg-card p-8 text-center">
          <Ruler className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-3 font-medium">This package can&apos;t be audited yet</p>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            The audit compares each suite&apos;s billed area to a BOMA measurement. Upload a BOMA report or floor plan
            area table, plus the rent roll or leases.
          </p>
          <button onClick={onUpload} className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
            Upload documents
          </button>
        </div>
      </div>
    )
  }

  const s = audit.summary
  const rows = [...audit.tenants].sort((a, b) => (b.totalGap ?? -Infinity) - (a.totalGap ?? -Infinity))
  const leverageLine = (Object.keys(LEVERAGE) as LeverageCall[])
    .filter((c) => s.leverage[c] && c !== 'MATCHES' && !(c === 'NO_LEASE' && s.pendingUpside))
    .map((c) => `${s.leverage[c]} ${LEVERAGE[c].label.toLowerCase()}`)
    .join(' · ')

  return (
    <div className="space-y-6">
      {header}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Not collected per year"
          value={money(s.totalUpside ?? 0)}
          sub={
            s.camUpside
              ? `${money(s.baseRentUpside)} base rent + ${money(s.camUpside)} CAM on ${sf(s.underbilledSF)} SF`
              : `${sf(s.underbilledSF)} SF across ${s.suitesUnderbilled} suite(s)`
          }
          tone={s.totalUpside ? 'good' : undefined}
        />
        <Stat
          label="Correctable under leases on file"
          value={money(s.collectibleUpside ?? 0)}
          sub={
            s.pendingUpside
              ? [`${money(s.pendingUpside)} more waiting on ${s.leverage.NO_LEASE ?? 0} lease(s)`, leverageLine].filter(Boolean).join(' · ')
              : leverageLine || 'No gaps above 2%'
          }
        />
        <Stat
          label="Load factor billed → BOMA"
          value={s.billedLoadFactor && s.bomaLoadFactor ? `${s.billedLoadFactor.toFixed(3)} → ${s.bomaLoadFactor.toFixed(3)}` : '—'}
          sub="Billed RSF ÷ BOMA usable SF, against the measured load factor"
          tone={s.billedLoadFactor && s.bomaLoadFactor && s.billedLoadFactor < s.bomaLoadFactor - 0.02 ? 'warn' : undefined}
        />
        <Stat
          label="CAM rate"
          value={s.camRatePSF ? `${money(s.camRatePSF, 2)}/SF` : '—'}
          sub={s.expensePool ? `${money(s.expensePool)}/yr pool · ${s.expensePoolBasis}` : 'No expense figures in this package'}
        />
      </div>

      {s.suitesOverbilled > 0 && (
        <div className="rounded-lg border border-destructive/30 bg-destructive-soft px-4 py-3 text-sm">
          <span className="font-medium text-destructive">{s.suitesOverbilled} tenant(s) billed on more area than measured</span>
          <span className="text-muted-foreground">
            {' '}
            — {sf(s.overbilledSF)} SF
            {s.overbilledExposure ? `, about ${money(s.overbilledExposure)}/yr they could claim back` : ''}.
          </span>
        </div>
      )}

      <div className="rounded-lg border border-border bg-card">
        <div className="border-b border-border px-4 py-3">
          <h3 className="font-semibold">By suite</h3>
          <p className="text-xs text-muted-foreground">
            {s.suitesMeasured} suites measured · biggest gaps first · tap a suite for its lease terms
          </p>
        </div>
        {/* Phones and iPads in portrait: one card per suite, dollars up front. */}
        <ul className="divide-y divide-border min-[1100px]:hidden">
          {rows.map((r) => {
            const isOpen = open === r.tenantId
            return (
              <li key={r.tenantId}>
                <button
                  className="w-full p-4 text-left"
                  aria-expanded={isOpen}
                  onClick={() => setOpen(isOpen ? null : r.tenantId)}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="font-medium">{r.name}</p>
                      <p className="text-xs text-muted-foreground">{r.suite || 'Suite not listed'}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-lg font-semibold tabular-nums">{gap(r.totalGap)}</p>
                      <p className="text-xs text-muted-foreground">per year</p>
                    </div>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                    <div>
                      <p className="text-xs text-muted-foreground">Billed → BOMA</p>
                      <p className="tabular-nums">
                        {sf(r.billedRsf)} → {sf(r.bomaRsf)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">Base rent</p>
                      <p className="tabular-nums">{gap(r.baseRentGap)}</p>
                    </div>
                    <div>
                      <p className="text-xs text-muted-foreground">CAM</p>
                      <p className="tabular-nums">{gap(r.camGap)}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-2">
                    {r.leverage.call ? (
                      <span className={cn('inline-flex border px-2 py-0.5 text-xs font-medium', LEVERAGE[r.leverage.call].style)}>
                        {LEVERAGE[r.leverage.call].label}
                      </span>
                    ) : (
                      <span />
                    )}
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      {isOpen ? 'Hide' : 'Lease terms'}
                      {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                    </span>
                  </div>
                </button>
                {isOpen && (
                  <div className="px-4 pb-5">
                    <Detail row={r} />
                  </div>
                )}
              </li>
            )
          })}
        </ul>
        <div className="hidden overflow-x-auto min-[1100px]:block">
          <Table className="text-[13px]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-6" />
                <TableHead className="min-w-[150px]">Tenant</TableHead>
                <TableHead className="text-right">Billed SF</TableHead>
                <TableHead className="text-right">BOMA SF</TableHead>
                <TableHead className="text-right">Gap</TableHead>
                <TableHead className="text-right">Share stated → BOMA</TableHead>
                <TableHead className="text-right">Base rent gap</TableHead>
                <TableHead className="text-right">CAM gap</TableHead>
                <TableHead className="text-right">Total / yr</TableHead>
                <TableHead>Leverage</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => {
                const key = r.tenantId
                const isOpen = open === key
                return (
                  <Fragment key={key}>
                    <TableRow className="cursor-pointer" onClick={() => setOpen(isOpen ? null : key)}>
                      <TableCell className="pr-0 text-muted-foreground">
                        {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                      </TableCell>
                      <TableCell>
                        <div className="font-medium">{r.name}</div>
                        <div className="text-xs text-muted-foreground">{r.suite || 'Suite not listed'}</div>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{sf(r.billedRsf)}</TableCell>
                      <TableCell className="text-right tabular-nums">{sf(r.bomaRsf)}</TableCell>
                      <TableCell
                        className={cn(
                          'text-right tabular-nums',
                          r.deltaPct !== null && r.deltaPct > 2 && 'text-success',
                          r.deltaPct !== null && r.deltaPct < -2 && 'text-destructive'
                        )}
                      >
                        {r.deltaSF === null ? '—' : `${r.deltaSF > 0 ? '+' : ''}${sf(r.deltaSF)}`}
                        {r.deltaPct !== null && <div className="text-xs text-muted-foreground">{r.deltaPct.toFixed(1)}%</div>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {share(r.billedShare)} → {share(r.bomaShare)}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{gap(r.baseRentGap)}</TableCell>
                      <TableCell className="text-right tabular-nums">{gap(r.camGap)}</TableCell>
                      <TableCell className="text-right font-medium tabular-nums">{gap(r.totalGap)}</TableCell>
                      <TableCell>
                        {r.leverage.call && (
                          <span className={cn('inline-flex border px-2 py-0.5 text-xs font-medium', LEVERAGE[r.leverage.call].style)}>
                            {LEVERAGE[r.leverage.call].label}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow className="hover:bg-transparent">
                        <TableCell />
                        <TableCell colSpan={9} className="whitespace-normal pb-5">
                          <Detail row={r} />
                        </TableCell>
                      </TableRow>
                    )}
                  </Fragment>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </div>

      <p className="text-xs leading-relaxed text-muted-foreground">
        Base rent gap = (BOMA SF − billed SF) × the tenant&apos;s rent per SF. CAM gap = expense pool × BOMA share − CAM
        billed; where the documents don&apos;t show what was billed, it&apos;s estimated as billed SF × the pool rate. Leverage
        is read from each lease&apos;s remeasurement and &quot;deemed area&quot; language — check the quoted clause before
        acting on it.
      </p>
    </div>
  )
}

function Detail({ row }: { row: LeaseAuditRow }) {
  const terms = Object.entries(row.terms).filter(([, v]) => v !== null && v !== '')
  return (
    <div className="grid gap-4 text-sm lg:grid-cols-2">
      <div className="space-y-2">
        <p>
          <span className="font-medium">{row.leverage.reason}.</span>
        </p>
        {row.leverage.clause && (
          <blockquote className="border-l-2 border-border pl-3 text-muted-foreground">&ldquo;{row.leverage.clause}&rdquo;</blockquote>
        )}
        {row.expenseNote && <p className="text-muted-foreground">{row.expenseNote}.</p>}
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
          <dt>Rent at BOMA area</dt>
          <dd className="tabular-nums text-foreground">
            {row.correctedAnnualRent ? `${money(row.correctedAnnualRent)}/yr at ${money(row.rentPSF, 2)}/SF` : '—'}
          </dd>
          <dt>CAM at BOMA share</dt>
          <dd className="tabular-nums text-foreground">{row.correctCam !== null ? `${money(row.correctCam)}/yr` : '—'}</dd>
          <dt>CAM billed</dt>
          <dd className="tabular-nums text-foreground">
            {row.billedCam !== null ? `${money(row.billedCam)}/yr` : '—'}
            {row.billedCamBasis && <span className="text-muted-foreground"> · {row.billedCamBasis}</span>}
          </dd>
          <dt>Load factor billed → BOMA</dt>
          <dd className="tabular-nums text-foreground">
            {row.billedLoadFactor && row.bomaLoadFactor ? `${row.billedLoadFactor.toFixed(3)} → ${row.bomaLoadFactor.toFixed(3)}` : '—'}
          </dd>
          <dt>Billed area from</dt>
          <dd className="text-foreground">{row.billedRsfSource ?? '—'}</dd>
        </dl>
      </div>
      <div>
        <p className="mb-2 font-medium">Expense terms in the lease</p>
        {terms.length ? (
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-muted-foreground">
            {terms.map(([k, v]) => (
              <Fragment key={k}>
                <dt>{TERM_LABELS[k] ?? k}</dt>
                <dd className="text-foreground">{String(v)}</dd>
              </Fragment>
            ))}
          </dl>
        ) : (
          <p className="text-muted-foreground">{row.leaseFile ? 'The lease states none of these terms.' : 'No lease in the package.'}</p>
        )}
        {row.leaseFile && <p className="mt-2 text-xs text-muted-foreground">Source: {row.leaseFile}</p>}
      </div>
    </div>
  )
}

function Stat({ label, value, sub, tone }: { label: string; value: string; sub?: string; tone?: 'good' | 'warn' }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="eyebrow">{label}</div>
      <div className={cn('mt-2 text-2xl font-semibold tabular-nums text-brand-navy', tone === 'good' && 'text-success', tone === 'warn' && 'text-warning')}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  )
}

function share(v: number | null) {
  return v === null ? '—' : `${v.toFixed(2)}%`
}

function gap(v: number | null) {
  if (v === null) return '—'
  if (Math.abs(v) < 0.5) return '$0'
  return `${v > 0 ? '+' : '−'}${money(Math.abs(v))}`
}
