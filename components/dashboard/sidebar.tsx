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
  { id: 'audit', label: 'Audit Log', icon: AlertTriangle },
  { id: 'rent-roll', label: 'Rent Roll', icon: Table2 },
  { id: 'lease-audit', label: 'Lease Audit', icon: FileText },
  { id: 'risk', label: 'Risk Dashboard', icon: Shield },
  { id: 'abstracts', label: 'Lease Abstracts', icon: FileStack },
  { id: 'upload', label: 'Upload Documents', icon: Upload },
]

export function Sidebar({ activeTab, onTabChange, deal }: SidebarProps) {
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-border bg-sidebar md:flex">
      <nav className="flex-1 p-3">
        <ul className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.id}>
                <button
                  onClick={() => onTabChange(item.id)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    item.id === 'upload' && 'mt-4',
                    activeTab === item.id
                      ? 'bg-sidebar-accent text-sidebar-foreground'
                      : 'text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'
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
      <div className="border-t border-sidebar-border p-4 text-xs text-muted-foreground">
        {deal.isSample ? 'Sample analysis' : 'Analyzed'}
        <br />
        <span className="text-sidebar-foreground">{timestamp(deal.submittedAt)}</span>
      </div>
    </aside>
  )
}

export function MobileTabs({ activeTab, onTabChange }: Omit<SidebarProps, 'deal'>) {
  return (
    <div className="-mx-4 mb-4 flex gap-1 overflow-x-auto border-b border-border px-4 pb-2 md:hidden">
      {navItems.map((item) => (
        <button
          key={item.id}
          onClick={() => onTabChange(item.id)}
          className={cn(
            'shrink-0 rounded-md px-3 py-1.5 text-sm font-medium',
            activeTab === item.id ? 'bg-secondary text-foreground' : 'text-muted-foreground'
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  )
}
