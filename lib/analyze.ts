import { DealAnalysis } from './types'

// On Vercel the Python service is mounted at /backend (see vercel.json).
// For local dev, next.config.mjs rewrites /backend to BACKEND_URL (default http://localhost:8000).
const BACKEND = (process.env.NEXT_PUBLIC_BACKEND_URL || '/backend').replace(/\/$/, '')

// Vercel functions reject request bodies over 4.5 MB. Raise this only when the
// backend runs somewhere without that limit.
export const MAX_UPLOAD_BYTES =
  Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB || 4.4) * 1024 * 1024

export const ACCEPTED_FILES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.ms-excel': ['.xls'],
  'text/csv': ['.csv'],
  'text/plain': ['.txt'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
}

export interface AnalyzeResult {
  analysis: DealAnalysis
  errors: string[]
}

export async function analyzeDeal(dealName: string, files: File[]): Promise<AnalyzeResult> {
  const form = new FormData()
  form.append('deal_name', dealName)
  for (const file of files) form.append('files', file, file.name)

  let response: Response
  try {
    response = await fetch(`${BACKEND}/analyze`, { method: 'POST', body: form })
  } catch {
    throw new Error('Could not reach the analysis service. Check your connection and try again.')
  }

  if (!response.ok) {
    throw new Error(await describeError(response))
  }

  const body = await response.json()
  if (!body?.analysis) {
    throw new Error('The analysis finished but returned no results.')
  }
  return { analysis: body.analysis as DealAnalysis, errors: body.errors ?? [] }
}

async function describeError(response: Response): Promise<string> {
  if (response.status === 413) {
    return 'The upload is too large for one request. Remove the largest files or split the package and try again.'
  }
  if (response.status === 504) {
    return 'The analysis took longer than the server allows. Try fewer documents at once.'
  }
  const raw = await response.text()
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // not JSON
  }
  return `Analysis failed (${response.status}). ${raw.slice(0, 200)}`.trim()
}
