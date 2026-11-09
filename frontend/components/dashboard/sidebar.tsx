'use client'

import { cn } from '@/lib/utils'
import {
  LayoutDashboard,
  AlertTriangle,
  Table2,
  FileText,
  Shield,
  FileStack,
  Upload,
  Ruler,
} from 'lucide-react'
import { timestamp } from '@/lib/format'
import { DealAnalysis, TabId } from '@/lib/types'

interface SidebarProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
  deal: DealAnalysis
}

const navItems: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: 'snapshot', label: 'Deal Snapshot', icon: LayoutDashboard },
  { id: 'lease-audit', label: 'Lease Audit', icon: Ruler },
  { id: 'audit', label: 'Audit Log', icon: AlertTriangle },
  { id: 'rent-roll', label: 'Rent Roll', icon: Table2 },
  { id: 'expirations', label: 'Lease Expirations', icon: FileText },
  { id: 'risk', label: 'Risk Dashboard', icon: Shield },
  { id: 'abstracts', label: 'Lease Abstracts', icon: FileStack },
  { id: 'upload', label: 'Upload Documents', icon: Upload },
]

export function Sidebar({ activeTab, onTabChange, deal }: SidebarProps) {
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-sidebar xl:flex">
      <nav className="flex-1 p-3">
        <ul className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.id}>
                <button
                  onClick={() => onTabChange(item.id)}
                  className={cn(
                    'flex w-full items-center gap-3 border-l-[3px] px-3 py-2.5 text-sm font-medium transition-colors',
                    item.id === 'upload' && 'mt-4',
                    activeTab === item.id
                      ? 'border-gold bg-sidebar-accent text-white'
                      : 'border-transparent text-white/70 hover:bg-sidebar-accent hover:text-white'
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </button>
              </li>
            )
          })}
        </ul>
      </nav>
      <div className="border-t border-sidebar-border p-4 text-xs text-white/60">
        {deal.isSample ? 'Sample analysis' : 'Analyzed'}
        <br />
        <span className="text-white">{timestamp(deal.submittedAt)}</span>
      </div>
    </aside>
  )
}

export function MobileTabs({ activeTab, onTabChange }: Omit<SidebarProps, 'deal'>) {
  return (
    <div className="sticky -top-4 z-20 -mx-4 -mt-4 mb-4 flex overflow-x-auto border-b border-border bg-white px-4 [scrollbar-width:none] md:-top-6 md:-mx-6 md:-mt-6 md:px-6 xl:hidden">
      {navItems.map((item) => (
        <button
          key={item.id}
          onClick={() => onTabChange(item.id)}
          className={cn(
            'shrink-0 border-b-[3px] px-3 py-2.5 text-sm font-medium',
            activeTab === item.id ? 'border-gold text-brand-navy' : 'border-transparent text-muted-foreground'
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
