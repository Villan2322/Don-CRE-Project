'use client'

import { cn } from '@/lib/utils'
import { CheckCircle2, AlertTriangle, Info, AlertCircle, ChevronDown, ChevronUp } from 'lucide-react'
import { useState } from 'react'

interface TraceEntry {
  timestamp: string
  stage: string
  message: string
  level: 'info' | 'success' | 'warning' | 'error'
  data?: Record<string, unknown>
}

interface PipelineTraceProps {
  logs: TraceEntry[]
  tenantCount: number
  charsExtracted?: number
}

const levelConfig = {
  info:    { icon: Info,         color: 'text-muted-foreground', dot: 'bg-muted-foreground' },
  success: { icon: CheckCircle2, color: 'text-emerald-400',      dot: 'bg-emerald-400' },
  warning: { icon: AlertTriangle,color: 'text-amber-400',        dot: 'bg-amber-400' },
  error:   { icon: AlertCircle,  color: 'text-destructive',      dot: 'bg-destructive' },
}

const STAGE_LABELS: Record<string, string> = {
  START:    'Start',
  BASELINE: 'PA Baseline',
  STAGE_1:  'Ingest',
  INGEST:   'Ingest',
  STAGE_2:  'Classify',
  CLASSIFY: 'Classify',
  STAGE_3:  'Extract',
  EXTRACT:  'Extract',
  STAGE_4:  'Synthesize',
  STAGE_5:  'Report',
}

export function PipelineTrace({ logs, tenantCount, charsExtracted }: PipelineTraceProps) {
  const [expanded, setExpanded] = useState(false)

  if (!logs || logs.length === 0) return null

  const errors   = logs.filter(l => l.level === 'error')
  const warnings = logs.filter(l => l.level === 'warning')
  const extractLogs = logs.filter(l => l.stage === 'EXTRACT')

  return (
    <div className="rounded-lg border border-border bg-card overflow-hidden">
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

      {/* Summary row — always visible */}
      <div className="border-t border-border px-4 py-3 grid grid-cols-3 gap-4 text-center text-sm">
        <div>
          <div className="text-lg font-bold text-foreground">{tenantCount}</div>
          <div className="text-xs text-muted-foreground">Tenants extracted</div>
        </div>
        <div>
          <div className="text-lg font-bold text-foreground">{extractLogs.length}</div>
          <div className="text-xs text-muted-foreground">Extraction passes</div>
        </div>
        <div>
          <div className={cn('text-lg font-bold', errors.length > 0 ? 'text-destructive' : 'text-emerald-400')}>
            {errors.length > 0 ? 'Errors' : 'OK'}
          </div>
          <div className="text-xs text-muted-foreground">Pipeline status</div>
        </div>
      </div>

      {/* Full log — expandable */}
      {expanded && (
        <div className="border-t border-border divide-y divide-border max-h-[480px] overflow-y-auto">
          {logs.map((entry, i) => {
            const cfg = levelConfig[entry.level] ?? levelConfig.info
            const Icon = cfg.icon
            const stageLabel = STAGE_LABELS[entry.stage] ?? entry.stage
            return (
              <div key={i} className="flex items-start gap-3 px-4 py-2.5">
                <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
                  <Icon className={cn('h-3.5 w-3.5', cfg.color)} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                      {stageLabel}
                    </span>
                    <span className={cn('text-xs', cfg.color, entry.level === 'info' ? 'text-foreground/80' : '')}>
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
