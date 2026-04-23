'use client'

import { useState } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'
import { mockDealAnalysis } from '@/lib/mock-data'
import { DealAnalysis, TabId } from '@/lib/types'

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('upload')
  const [deal, setDeal] = useState<DealAnalysis>(mockDealAnalysis)
  const [isLoading, setIsLoading] = useState(false)

  function handleAnalysisComplete(result: DealAnalysis) {
    setDeal(result)
    setActiveTab('snapshot')
  }

  return (
    <div className="flex h-screen flex-col bg-background">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />
        <main className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex h-full items-center justify-center">
              <p className="text-muted-foreground">Loading analysis results...</p>
            </div>
          ) : (
            <TabContent
              activeTab={activeTab}
              deal={deal}
              onAnalysisComplete={handleAnalysisComplete}
            />
          )}
        </main>
      </div>
    </div>
  )
}
