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
  Clock,
  Calculator,
} from 'lucide-react'
import { TabId } from '@/lib/types'

interface SidebarProps {
  activeTab: TabId
  onTabChange: (tab: TabId) => void
}

const navItems: { id: TabId; label: string; icon: React.ElementType }[] = [
  { id: 'snapshot', label: 'Deal Snapshot', icon: LayoutDashboard },
  { id: 'audit', label: 'Audit Log', icon: AlertTriangle },
  { id: 'rent-roll', label: 'Rent Roll', icon: Table2 },
  { id: 'lease-audit', label: 'Lease Audit', icon: FileText },
  { id: 'cam', label: 'CAM Reconciliation', icon: Calculator },
  { id: 'risk', label: 'Risk Dashboard', icon: Shield },
  { id: 'abstracts', label: 'Lease Abstracts', icon: FileStack },
]

export function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  return (
    <aside className="flex w-56 flex-col border-r border-border bg-sidebar">
      <nav className="flex-1 p-3">
        <div className="mb-2 px-3 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Analysis
        </div>
        <ul className="space-y-0.5">
          {navItems.map((item) => {
            const Icon = item.icon
            return (
              <li key={item.id}>
                <button
                  onClick={() => onTabChange(item.id)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
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
        <div className="mb-2 mt-6 px-3 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Actions
        </div>
        <ul className="space-y-0.5">
          <li>
            <button
              onClick={() => onTabChange('upload')}
              className={cn(
                'flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                activeTab === 'upload'
                  ? 'bg-sidebar-accent text-sidebar-foreground'
                  : 'text-muted-foreground hover:bg-sidebar-accent/50 hover:text-sidebar-foreground'
              )}
            >
              <Upload className="h-4 w-4" />
              Upload Documents
            </button>
          </li>
          <li>
            <button className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent/50 hover:text-sidebar-foreground">
              <Clock className="h-4 w-4" />
              History
            </button>
          </li>
        </ul>
      </nav>
      <div className="border-t border-sidebar-border p-4">
        <div className="text-xs text-muted-foreground">
          Last updated
          <br />
          <span className="text-sidebar-foreground">April 18, 2026 2:32 PM</span>
        </div>
      </div>
    </aside>
  )
}
