'use client'

import { useEffect, useRef, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import type { DealAnalysis } from '@/lib/types'

// ─── Types ────────────────────────────────────────────────────────────────────

interface AgentEvent {
  type: 'agent_start' | 'agent_complete' | 'agent_error' | 'analysis_complete' | 'analysis_error'
  agentId: string
  agentName: string
  description: string
  startedAt?: number
  completedAt?: number
  durationMs?: number
  outputPreview?: string
  error?: string
  result?: unknown
}

interface AgentRow {
  id: string
  name: string
  description: string
  status: 'pending' | 'running' | 'complete' | 'error'
  startedAt?: number
  durationMs?: number
  outputPreview?: string
  error?: string
}

const AGENT_ORDER: { id: string; name: string; description: string }[] = [
  {
    id: 'rent_roll',
    name: 'Rent Roll Analyst',
    description: 'Extracts tenant roster, rents, lease dates, WALT, NOI',
  },
  {
    id: 'lease_abstraction',
    name: 'Lease Abstraction',
    description: 'Escalations, expense structure, TI, CAM caps, renewal options',
  },
  {
    id: 'rsf_reconciliation',
    name: 'RSF Reconciliation',
    description: 'Cross-checks SF across rent roll, leases, and BOMA',
  },
  {
    id: 'red_flag',
    name: 'Red Flag Detection',
    description: 'Co-tenancy clauses, near-expiry leases, concentration risk',
  },
  {
    id: 'risk_scoring',
    name: 'Risk Scoring',
    description: '0-100 deal score, tier, 6 sub-scores, next-step recommendations',
  },
]

// ─── Sub-components ───────────────────────────────────────────────────────────

function StatusDot({ status }: { status: AgentRow['status'] }) {
  return (
    <span
      className={cn(
        'mt-0.5 h-2.5 w-2.5 shrink-0 rounded-full',
        status === 'pending'  && 'bg-muted-foreground/30',
        status === 'running'  && 'animate-pulse bg-primary',
        status === 'complete' && 'bg-green-500',
        status === 'error'    && 'bg-destructive',
      )}
    />
  )
}

function DurationBadge({ ms }: { ms: number }) {
  const label = ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
  return (
    <Badge variant="outline" className="font-mono text-xs">
      {label}
    </Badge>
  )
}

function AgentRowItem({ row, index }: { row: AgentRow; index: number }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => row.status === 'complete' && setExpanded((v) => !v)}
        className={cn(
          'flex w-full items-start gap-3 px-4 py-3 text-left transition-colors',
          row.status === 'complete' && 'hover:bg-muted/40 cursor-pointer',
          row.status !== 'complete' && 'cursor-default',
        )}
      >
        {/* Step number */}
        <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-muted text-[10px] font-semibold text-muted-foreground">
          {index + 1}
        </span>

        <StatusDot status={row.status} />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className={cn(
                'text-sm font-medium',
                row.status === 'pending' && 'text-muted-foreground',
                row.status === 'running' && 'text-foreground',
                row.status === 'complete' && 'text-foreground',
                row.status === 'error' && 'text-destructive',
              )}
            >
              {row.name}
            </span>
            {row.status === 'running' && (
              <span className="text-xs text-primary animate-pulse">running...</span>
            )}
            {row.status === 'error' && (
              <span className="text-xs text-destructive">failed</span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{row.description}</p>
          {row.status === 'error' && row.error && (
            <p className="mt-1 text-xs text-destructive">{row.error}</p>
          )}
        </div>

        {row.durationMs != null && <DurationBadge ms={row.durationMs} />}

        {row.status === 'complete' && (
          <span className="mt-0.5 text-xs text-muted-foreground">{expanded ? '▲' : '▼'}</span>
        )}
      </button>

      {expanded && row.outputPreview && (
        <div className="border-t border-border bg-muted/30 px-4 py-3">
          <p className="mb-1 text-xs font-medium text-muted-foreground">Raw output preview</p>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all font-mono text-[11px] text-foreground/80">
            {row.outputPreview}
          </pre>
        </div>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

interface AgentTraceProps {
  dealId: string
  documentIds: string[]
  knownSf?: { boma_sf?: number | null; rent_roll_sf?: number | null; lease_sf?: number | null }
  dealName?: string
  onComplete: (result: DealAnalysis) => void
  onError: (message: string) => void
}

export function AgentTrace({
  dealId,
  documentIds,
  knownSf,
  dealName,
  onComplete,
  onError,
}: AgentTraceProps) {
  const [rows, setRows] = useState<AgentRow[]>(
    AGENT_ORDER.map((a) => ({ ...a, status: 'pending' as const })),
  )
  const [elapsedMs, setElapsedMs] = useState(0)
  const startRef  = useRef(Date.now())
  const timerRef  = useRef<ReturnType<typeof setInterval> | null>(null)
  const abortRef  = useRef<AbortController | null>(null)

  function updateRow(agentId: string, patch: Partial<AgentRow>) {
    setRows((prev) =>
      prev.map((r) => (r.id === agentId ? { ...r, ...patch } : r)),
    )
  }

  useEffect(() => {
    const abort = new AbortController()
    abortRef.current = abort
    startRef.current = Date.now()

    timerRef.current = setInterval(() => {
      setElapsedMs(Date.now() - startRef.current)
    }, 200)

    async function run() {
      try {
        const res = await fetch('/api/analyze/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          signal: abort.signal,
          body: JSON.stringify({
            deal_id: dealId,
            documents: documentIds,
            known_sf: knownSf,
            deal_name: dealName,
          }),
        })

        if (!res.ok || !res.body) {
          const err = await res.json().catch(() => ({ detail: 'Stream failed' }))
          throw new Error(err.detail ?? 'Stream failed')
        }

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() ?? ''

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue
            try {
              const event = JSON.parse(line.slice(6)) as AgentEvent

              if (event.type === 'agent_start') {
                updateRow(event.agentId, { status: 'running', startedAt: event.startedAt })
              } else if (event.type === 'agent_complete') {
                updateRow(event.agentId, {
                  status: 'complete',
                  durationMs: event.durationMs,
                  outputPreview: event.outputPreview,
                })
              } else if (event.type === 'agent_error') {
                updateRow(event.agentId, {
                  status: 'error',
                  durationMs: event.durationMs,
                  error: event.error,
                })
              } else if (event.type === 'analysis_complete') {
                if (timerRef.current) clearInterval(timerRef.current)
                onComplete(event.result as DealAnalysis)
              } else if (event.type === 'analysis_error') {
                if (timerRef.current) clearInterval(timerRef.current)
                onError((event as { error?: string }).error ?? 'Analysis failed')
              }
            } catch {
              // malformed SSE line — skip
            }
          }
        }
      } catch (err: unknown) {
        if ((err as { name?: string }).name === 'AbortError') return
        if (timerRef.current) clearInterval(timerRef.current)
        onError(err instanceof Error ? err.message : 'Analysis stream failed')
      }
    }

    run()

    return () => {
      abort.abort()
      if (timerRef.current) clearInterval(timerRef.current)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const totalDone  = rows.filter((r) => r.status === 'complete' || r.status === 'error').length
  const totalRun   = rows.filter((r) => r.status === 'running').length
  const allDone    = totalDone === rows.length

  const elapsedLabel =
    elapsedMs < 1000 ? `${elapsedMs}ms` : `${(elapsedMs / 1000).toFixed(1)}s`

  return (
    <Card className="border-border">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-semibold">Agent Trace</CardTitle>
          <div className="flex items-center gap-2">
            {!allDone && (
              <span className="text-xs text-muted-foreground">
                {elapsedLabel} elapsed
              </span>
            )}
            <Badge
              variant={allDone ? 'default' : 'secondary'}
              className={cn(
                allDone && 'bg-green-500 text-white',
              )}
            >
              {totalDone}/{rows.length} complete
              {totalRun > 0 && ' · 1 running'}
            </Badge>
          </div>
        </div>

        {/* Progress bar */}
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              'h-full rounded-full transition-all duration-500',
              allDone ? 'bg-green-500' : 'bg-primary',
            )}
            style={{ width: `${(totalDone / rows.length) * 100}%` }}
          />
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <div className="divide-y divide-border rounded-b-lg overflow-hidden">
          {rows.map((row, i) => (
            <AgentRowItem key={row.id} row={row} index={i} />
          ))}
        </div>
      </CardContent>
    </Card>
  )
}
