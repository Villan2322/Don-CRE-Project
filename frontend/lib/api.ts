const API_BASE = '/api'

export interface UploadResponse {
  message: string
  document_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
}

export interface Document {
  id: string
  filename: string
  document_type: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  uploaded_at: string
  processed_at: string | null
  page_count: number | null
  extracted_data: Record<string, unknown> | null
}

export interface AnalysisRequest {
  deal_id: string
  documents: string[]
}

export interface AnalysisResponse {
  deal_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  message: string
  result: AnalysisResult | null
}

export interface AnalysisResult {
  deal_id: string
  property_name: string
  property_address: string
  analysis_date: string
  deal_score: {
    overall_score: number
    tier: string
    sub_scores: Record<string, number>
    score_factors: Array<{ category: string; impact: number; reason: string }>
  }
  rsf_reconciliation: {
    total_rsf_rent_roll: number
    total_rsf_leases: number
    total_rsf_boma: number
    variance_rent_roll_vs_boma: number
    variance_percentage: number
    estimated_annual_revenue_impact: number
    discrepancies: Array<Record<string, unknown>>
  }
  tenants: unknown[]
  lease_abstracts: unknown[]
  red_flags: unknown[]
  documents_processed: Document[]
  what_to_get_next: string[]
  financial_summary: Record<string, number>
}

export interface Agent {
  name: string
  description: string
  input: string
  output: string
}

class APIClient {
  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }))
      throw new Error(error.detail || 'Request failed')
    }

    return response.json()
  }

  // Health check
  async health(): Promise<{ status: string; service: string }> {
    return this.request('/health')
  }

  // Document operations
  async uploadDocument(file: File): Promise<UploadResponse> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      throw new Error('Upload failed')
    }

    return response.json()
  }

  async listDocuments(): Promise<Document[]> {
    return this.request('/documents')
  }

  async getDocument(documentId: string): Promise<Document> {
    return this.request(`/documents/${documentId}`)
  }

  async deleteDocument(documentId: string): Promise<{ message: string }> {
    return this.request(`/documents/${documentId}`, {
      method: 'DELETE',
    })
  }

  // Analysis operations — sends files directly as multipart/form-data
  async runAnalysis(dealName: string, files: File[]): Promise<Record<string, unknown>> {
    const formData = new FormData()
    formData.append('deal_name', dealName)
    for (const file of files) {
      formData.append('files', file)
    }

    const response = await fetch(`${API_BASE}/analyze`, {
      method: 'POST',
      body: formData,
    })

    if (!response.ok) {
      const err = await response.json().catch(() => ({ error: 'Analysis failed' }))
      throw new Error(err.error || err.detail || 'Analysis failed')
    }

    return response.json()
  }

  async getDealAnalysis(dealId: string): Promise<AnalysisResult> {
    return this.request(`/deals/${dealId}`)
  }

  async getDealRawData(dealId: string): Promise<Record<string, unknown>> {
    return this.request(`/deals/${dealId}/raw`)
  }

  // Agent info
  async listAgents(): Promise<{ agents: Agent[] }> {
    return this.request('/agents')
  }
}

export const api = new APIClient()

// SWR fetcher
export const fetcher = async <T>(url: string): Promise<T> => {
  const response = await fetch(url)
  if (!response.ok) {
    throw new Error('Failed to fetch')
  }
  return response.json()
}
