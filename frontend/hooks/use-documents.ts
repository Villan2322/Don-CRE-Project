import useSWR from 'swr'
import { api, fetcher, Document, AnalysisResult, Agent } from '@/lib/api'

export function useDocuments() {
  const { data, error, isLoading, mutate } = useSWR<Document[]>(
    '/api/documents',
    fetcher,
    {
      refreshInterval: 5000, // Poll every 5 seconds for status updates
    }
  )

  return {
    documents: data || [],
    isLoading,
    isError: error,
    refresh: mutate,
  }
}

export function useDocument(documentId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<Document>(
    documentId ? `/api/documents/${documentId}` : null,
    fetcher
  )

  return {
    document: data,
    isLoading,
    isError: error,
    refresh: mutate,
  }
}

export function useDealAnalysis(dealId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<AnalysisResult>(
    dealId ? `/api/deals/${dealId}` : null,
    fetcher
  )

  return {
    analysis: data,
    isLoading,
    isError: error,
    refresh: mutate,
  }
}

export function useAgents() {
  const { data, error, isLoading } = useSWR<{ agents: Agent[] }>(
    '/api/agents',
    fetcher
  )

  return {
    agents: data?.agents || [],
    isLoading,
    isError: error,
  }
}

export async function uploadDocument(file: File) {
  return api.uploadDocument(file)
}

export async function runAnalysis(dealId: string, documentIds: string[]) {
  return api.runAnalysis(dealId, documentIds)
}

export async function deleteDocument(documentId: string) {
  return api.deleteDocument(documentId)
}
