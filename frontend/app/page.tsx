'use client'

import { useEffect, useState } from 'react'
import { Header } from '@/components/dashboard/header'
import { Sidebar } from '@/components/dashboard/sidebar'
import { TabContent } from '@/components/dashboard/tab-content'
import { sampleDeal } from '@/lib/mock-data'
import { loadHistory, removeAnalysis, saveAnalysis } from '@/lib/deal-history'
import { TabId, DealAnalysis, UploadMode } from '@/lib/types'
import { canAddDocuments } from '@/lib/carry'

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('snapshot')
  const [deal, setDeal] = useState<DealAnalysis>(sampleDeal)
  const [history, setHistory] = useState<DealAnalysis[]>([])
  const [uploadMode, setUploadMode] = useState<UploadMode>('new')

  const openUpload = (mode: UploadMode) => {
    setUploadMode(mode)
    setActiveTab('upload')
  }
  const changeTab = (tab: TabId) => {
    if (tab === 'upload') return openUpload(canAddDocuments(deal) ? 'add' : 'new')
    setActiveTab(tab)
  }

  useEffect(() => {
    const saved = loadHistory()
    setHistory(saved)
    if (saved.length) setDeal(saved[0])
  }, [])

  const handleAnalysisComplete = (analysis: DealAnalysis) => {
    setHistory(saveAnalysis(analysis))
    setDeal(analysis)
    setActiveTab('snapshot')
  }

  const handleSelect = (id: string) => {
    if (id === sampleDeal.id) return setDeal(sampleDeal)
    const found = history.find((a) => a.id === id)
    if (found) setDeal(found)
  }

  const handleRemove = (id: string) => {
    const next = removeAnalysis(id)
    setHistory(next)
    if (deal.id === id) setDeal(next[0] ?? sampleDeal)
  }

  return (
    <div className="flex h-dvh flex-col bg-background">
      <Header
        deal={deal}
        history={history}
        onSelect={handleSelect}
        onRemove={handleRemove}
        onNewAnalysis={() => openUpload('new')}
      />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar activeTab={activeTab} onTabChange={changeTab} deal={deal} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6">
          <TabContent
            activeTab={activeTab}
            deal={deal}
            history={history}
            onAnalysisComplete={handleAnalysisComplete}
            onTabChange={changeTab}
            uploadMode={uploadMode}
            onUploadModeChange={setUploadMode}
            onAddDocuments={() => openUpload('add')}
          />
        </main>
      </div>
    </div>
  )
}
