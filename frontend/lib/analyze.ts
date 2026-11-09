import { Carry, DealAnalysis } from './types'

// The Python server serves this app and the API from the same origin.
const API = (process.env.NEXT_PUBLIC_API_URL || '/api').replace(/\/$/, '')

export const MAX_UPLOAD_BYTES = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB || 100) * 1024 * 1024

export const ACCEPTED_FILES: Record<string, string[]> = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
  'application/vnd.ms-excel': ['.xls'],
  'text/csv': ['.csv'],
  'text/plain': ['.txt'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
}

const POLL_MS = 2000
const GIVE_UP_MS = 20 * 60 * 1000

export interface AnalyzeResult {
  analysis: DealAnalysis
  errors: string[]
}

// Starts an analysis job, then polls until it finishes. Polling keeps every
// request short, so no proxy or load balancer timeout can cut off a long run.
export async function analyzeDeal(
  dealName: string,
  files: File[],
  onStage?: (stage: string) => void,
  prior?: Carry
): Promise<AnalyzeResult> {
  const form = new FormData()
  form.append('deal_name', dealName)
  for (const file of files) form.append('files', file, file.name)
  if (prior) form.append('prior', new Blob([JSON.stringify(prior)], { type: 'application/json' }), 'prior.json')

  const started = await request(`${API}/analyze`, { method: 'POST', body: form })
  const jobId: string = started.job_id
  const deadline = Date.now() + GIVE_UP_MS

  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, POLL_MS))
    const job = await request(`${API}/jobs/${jobId}`)
    if (job.stage) onStage?.(job.stage)
    if (job.status === 'done') {
      if (!job.result?.analysis) throw new Error('The analysis finished but returned no results.')
      return { analysis: job.result.analysis as DealAnalysis, errors: job.result.errors ?? [] }
    }
    if (job.status === 'failed') throw new Error(job.error || 'The analysis failed.')
  }
  throw new Error('The analysis is taking unusually long. Check back in a few minutes or try fewer documents.')
}

async function request(url: string, init?: RequestInit) {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch {
    throw new Error('Could not reach the analysis service. Check your connection and try again.')
  }
  if (!response.ok) throw new Error(await describeError(response))
  return response.json()
}

async function describeError(response: Response): Promise<string> {
  if (response.status === 413) {
    return 'The upload is too large. Remove the largest files or split the package and try again.'
  }
  if (response.status === 404) {
    return 'The analysis job was not found. The server may have restarted — please run it again.'
  }
  const raw = await response.text()
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed.detail === 'string') return parsed.detail
  } catch {
    // not JSON
  }
  return `Request failed (${response.status}). ${raw.slice(0, 200)}`.trim()
}
