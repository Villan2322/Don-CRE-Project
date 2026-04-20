'use client'

import { cn } from '@/lib/utils'
import { CheckCircle2, AlertTriangle, Info, AlertCircle, ChevronDown, ChevronUp, ShieldCheck, ShieldAlert } from 'lucide-react'
import { useState } from 'react'

interface TraceEntry {
  timestamp: string
  stage: string
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
  data?: Record<string, unknown>
}

interface COVESummary {
  threshold_pct: number
  verified_tenants: number
  unverified_tenants: number
  total_tenants: number
  suppressed_fields: string[]
}

interface PipelineTraceProps {
  logs: TraceEntry[]
  tenantCount: number
  cove?: COVESummary
}

const levelConfig = {
  info:    { icon: Info,          color: 'text-muted-foreground/70' },
  success: { icon: CheckCircle2,  color: 'text-emerald-400' },
  warning: { icon: AlertTriangle, color: 'text-amber-400' },
  error:   { icon: AlertCircle,   color: 'text-destructive' },
}

const STAGE_LABELS: Record<string, string> = {
  START:    'Start',
  BASELINE: 'PA Baseline',
  INGEST:   'Ingest',
  HOP_1:    'Ingest',
  HOP_2:    'Classify',
  CLASSIFY: 'Classify',
  HOP_3:    'Extract',
  EXTRACT:  'Extract',
  HOP_4:    'COVE',
  HOP_5:    'Reconcile',
  HOP_6:    'Synthesize',
  HOP_7:    'Verify',
  HOP_8:    'Report',
  RESULT:   'Result',
  COMPLETE: 'Complete',
}

export function PipelineTrace({ logs, tenantCount, cove }: PipelineTraceProps) {
  const [expanded, setExpanded] = useState(false)

  if (!logs || logs.length === 0) return null

  const errors     = logs.filter(l => l.level === 'error')
  const warnings   = logs.filter(l => l.level === 'warning')
  const coveLog    = logs.filter(l => l.stage === 'HOP_4' || l.stage === 'COVE')

  const verifiedPct = cove && cove.total_tenants > 0
    ? Math.round((cove.verified_tenants / cove.total_tenants) * 100)
    : null

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      {/* Header */}
      <button
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-muted/20 transition-colors"
        onClick={() => setExpanded(v => !v)}
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold">Pipeline Trace</span>
          <span className="text-xs text-muted-foreground">{logs.length} steps</span>
          {errors.length > 0 && (
            <span className="rounded bg-destructive/20 px-1.5 py-0.5 text-xs text-destructive">
              {errors.length} error{errors.length !== 1 ? 's' : ''}
            </span>
          )}
          {warnings.length > 0 && (
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 text-xs text-amber-400">
              {warnings.length} warning{warnings.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>
        {expanded ? <ChevronUp className="h-4 w-4 text-muted-foreground" /> : <ChevronDown className="h-4 w-4 text-muted-foreground" />}
      </button>

      {/* Summary stats — always visible */}
      <div className="border-t border-border px-4 py-3 grid grid-cols-4 gap-4 text-center text-sm">
        <div>
          <div className="text-lg font-bold text-foreground">{tenantCount}</div>
          <div className="text-xs text-muted-foreground">Tenants found</div>
        </div>

        {/* COVE verification block */}
        <div>
          {verifiedPct !== null ? (
            <>
              <div className={cn(
                'text-lg font-bold',
                verifiedPct >= 90 ? 'text-emerald-400' : verifiedPct >= 70 ? 'text-amber-400' : 'text-destructive'
              )}>
                {verifiedPct}%
              </div>
              <div className="text-xs text-muted-foreground">COVE verified</div>
            </>
          ) : (
            <>
              <div className="text-lg font-bold text-muted-foreground">—</div>
              <div className="text-xs text-muted-foreground">COVE</div>
            </>
          )}
        </div>

        <div>
          {cove ? (
            <>
              <div className={cn('text-lg font-bold', cove.unverified_tenants > 0 ? 'text-amber-400' : 'text-emerald-400')}>
                {cove.unverified_tenants}
              </div>
              <div className="text-xs text-muted-foreground">Suppressed rows</div>
            </>
          ) : (
            <>
              <div className="text-lg font-bold text-muted-foreground">—</div>
              <div className="text-xs text-muted-foreground">Suppressed rows</div>
            </>
          )}
        </div>

        <div>
          <div className={cn('text-lg font-bold', errors.length > 0 ? 'text-destructive' : 'text-emerald-400')}>
            {errors.length > 0 ? 'Errors' : 'OK'}
          </div>
          <div className="text-xs text-muted-foreground">Status</div>
        </div>
      </div>

      {/* COVE detail — shown when there are suppressed rows */}
      {cove && cove.unverified_tenants > 0 && (
        <div className="border-t border-border bg-amber-500/5 px-4 py-3">
          <div className="flex items-start gap-2">
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-amber-400">
                {cove.unverified_tenants} tenant row{cove.unverified_tenants !== 1 ? 's' : ''} below {cove.threshold_pct}% confidence — numeric fields suppressed
              </p>
              {cove.suppressed_fields.slice(0, 4).map((s, i) => (
                <p key={i} className="mt-0.5 text-xs text-muted-foreground truncate">{s}</p>
              ))}
              {cove.suppressed_fields.length > 4 && (
                <p className="mt-0.5 text-xs text-muted-foreground">...and {cove.suppressed_fields.length - 4} more</p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* COVE all-green banner */}
      {cove && cove.unverified_tenants === 0 && cove.total_tenants > 0 && (
        <div className="border-t border-border bg-emerald-500/5 px-4 py-2.5 flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 shrink-0 text-emerald-400" />
          <p className="text-xs text-emerald-400 font-medium">
            All {cove.total_tenants} tenants verified at {'>'}={cove.threshold_pct}% confidence across {coveLog.length > 0 ? 'multiple' : ''} extraction passes
          </p>
        </div>
      )}

      {/* Full log — expandable */}
      {expanded && (
        <div className="border-t border-border divide-y divide-border max-h-[480px] overflow-y-auto">
          {logs.map((entry, i) => {
            const cfg       = levelConfig[entry.level] ?? levelConfig.info
            const Icon      = cfg.icon
            const stageLabel= STAGE_LABELS[entry.stage] ?? entry.stage
            const isCove    = entry.stage === 'HOP_4' || entry.stage === 'COVE'
            return (
              <div key={i} className={cn('flex items-start gap-3 px-4 py-2.5', isCove && 'bg-muted/10')}>
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
                  <Icon className={cn('h-3.5 w-3.5', cfg.color)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={cn(
                      'rounded px-1.5 py-0.5 text-[10px] font-mono',
                      isCove ? 'bg-amber-500/20 text-amber-400' : 'bg-muted text-muted-foreground'
                    )}>
                      {stageLabel}
                    </span>
                    <span className={cn('text-xs break-words', cfg.color, entry.level === 'info' && 'text-foreground/80')}>
                      {entry.message}
                    </span>
                  </div>
                </div>
                <span className="shrink-0 text-[10px] text-muted-foreground tabular-nums">
                  {new Date(entry.timestamp).toLocaleTimeString()}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
