'use client'

import { Building2, ChevronDown, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { sampleDeal } from '@/lib/mock-data'
import { timestamp } from '@/lib/format'
import { DealAnalysis } from '@/lib/types'

interface HeaderProps {
  deal: DealAnalysis
  history: DealAnalysis[]
  onSelect: (id: string) => void
  onRemove: (id: string) => void
  onNewAnalysis: () => void
}

export function Header({ deal, history, onSelect, onRemove, onNewAnalysis }: HeaderProps) {
  return (
    <header className="flex items-center justify-between gap-3 border-b border-border bg-card px-4 py-3 md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex shrink-0 items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary">
            <Building2 className="h-4 w-4 text-primary-foreground" />
          </div>
          <span className="hidden text-lg font-semibold sm:inline">CRE Intelligence</span>
        </div>
        <span className="hidden text-muted-foreground sm:inline">/</span>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="min-w-0 gap-1.5">
              <span className="truncate">{deal.dealName}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-80">
            <DropdownMenuLabel className="text-xs text-muted-foreground">Saved in this browser</DropdownMenuLabel>
            {history.length === 0 && (
              <div className="px-2 py-1.5 text-sm text-muted-foreground">No analyses yet</div>
            )}
            {history.map((a) => (
              <DropdownMenuItem key={a.id} onSelect={() => onSelect(a.id)} className="group gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{a.dealName}</div>
                  <div className="text-xs text-muted-foreground">
                    {a.score}/100 · {timestamp(a.submittedAt)}
                  </div>
                </div>
                <button
                  type="button"
                  aria-label={`Remove ${a.dealName}`}
                  className="rounded p-1 text-muted-foreground opacity-0 hover:text-destructive group-hover:opacity-100 group-focus:opacity-100"
                  onClick={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    onRemove(a.id)
                  }}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => onSelect(sampleDeal.id)}>
              <span className="text-muted-foreground">View sample analysis</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {deal.isSample && (
          <Badge variant="outline" className="hidden shrink-0 border-warning/40 text-warning sm:inline-flex">
            Sample data
          </Badge>
        )}
      </div>
      <Button size="sm" onClick={onNewAnalysis} className="shrink-0">
        <Plus className="h-4 w-4 sm:mr-1.5" />
        <span className="hidden sm:inline">New analysis</span>
      </Button>
    </header>
  )
}
