'use client'

import { ChevronDown, Plus, Trash2 } from 'lucide-react'
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
    <header className="flex items-center justify-between gap-3 border-b border-border bg-white px-4 pb-2 pt-[max(0.5rem,env(safe-area-inset-top))] md:px-6">
      <div className="flex min-w-0 items-center gap-3 md:gap-4">
        <div className="flex shrink-0 items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src="/bluecpm-logo.png" alt="Blue Commercial Properties" width={66} height={48} className="h-11 w-auto md:h-12" />
          <div className="hidden border-l border-border pl-3 lg:block">
            <div className="eyebrow leading-tight">Deal</div>
            <div className="eyebrow leading-tight">Intelligence</div>
          </div>
        </div>
        <span className="hidden h-8 w-px bg-border sm:block lg:hidden" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-10 min-w-0 gap-1.5 text-brand-navy hover:bg-accent">
              <span className="truncate font-semibold">{deal.dealName}</span>
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
                  className="rounded p-2 text-muted-foreground hover:text-destructive [@media(hover:hover)]:opacity-0 [@media(hover:hover)]:group-hover:opacity-100 [@media(hover:hover)]:group-focus:opacity-100"
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
          <Badge variant="outline" className="hidden shrink-0 border-gold bg-gold-soft font-medium text-brand-navy sm:inline-flex">
            Sample data
          </Badge>
        )}
      </div>
      <Button onClick={onNewAnalysis} className="h-10 shrink-0 bg-brand-navy px-4 font-semibold text-white hover:bg-brand-navy-deep">
        <Plus className="h-4 w-4 sm:mr-1.5" />
        <span className="hidden sm:inline">New analysis</span>
      </Button>
    </header>
  )
}
