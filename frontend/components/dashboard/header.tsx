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
    <header className="flex items-center justify-between gap-3 border-b-2 border-gold bg-brand-navy px-4 pb-2.5 pt-[max(0.625rem,env(safe-area-inset-top))] text-white md:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <div className="flex shrink-0 items-center gap-2.5">
          <div className="flex h-9 w-9 items-center justify-center rounded-sm bg-white/10 ring-1 ring-white/20">
            <Building2 className="h-[18px] w-[18px] text-gold" />
          </div>
          <div className="hidden leading-tight sm:block">
            <div className="font-heading text-[15px] font-bold tracking-tight">Deal Intelligence</div>
            <div className="text-[10px] font-medium uppercase tracking-[0.14em] text-white/60">Blue Commercial Properties</div>
          </div>
        </div>
        <span className="hidden h-7 w-px bg-white/20 sm:block" />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-10 min-w-0 gap-1.5 text-white hover:bg-white/10 hover:text-white">
              <span className="truncate font-medium">{deal.dealName}</span>
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-white/60" />
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
          <Badge variant="outline" className="hidden shrink-0 border-gold/60 text-gold sm:inline-flex">
            Sample data
          </Badge>
        )}
      </div>
      <Button onClick={onNewAnalysis} className="h-10 shrink-0 rounded-sm bg-gold px-4 font-semibold text-gold-foreground hover:bg-gold/90">
        <Plus className="h-4 w-4 sm:mr-1.5" />
        <span className="hidden sm:inline">New analysis</span>
      </Button>
    </header>
  )
}
