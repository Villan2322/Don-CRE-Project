'use client'

import { useState } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'

import { TabId, DealAnalysis } from '@/lib/types'

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('snapshot')
  const [dealAnalysis, setDealAnalysis] = useState<DealAnalysis | null>(null)

  const handleAnalysisComplete = (analysis: DealAnalysis) => {
    setDealAnalysis(analysis)
    setActiveTab('snapshot')
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header dealName={dealAnalysis?.dealName} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
        <main className="flex-1 overflow-y-auto p-6">
          <TabContent 
            activeTab={activeTab} 
            deal={dealAnalysis} 
            onAnalysisComplete={handleAnalysisComplete}
          />
        </main>
      </div>
    </div>
  )
}
