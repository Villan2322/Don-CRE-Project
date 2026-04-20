'use client'

import { useState } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'
import { mockDealAnalysis } from '@/lib/mock-data'
import { TabId } from '@/lib/types'

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('snapshot')

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
        <main className="flex-1 overflow-y-auto p-6">
          <TabContent activeTab={activeTab} deal={mockDealAnalysis} />
        </main>
      </div>
    </div>
  )
}
