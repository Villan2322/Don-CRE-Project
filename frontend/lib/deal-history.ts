import { DealAnalysis } from './types'

// Analyses live in this browser only — the backend keeps nothing between requests.
const KEY = 'cre-intel:analyses:v2'
const MAX_SAVED = 15

export interface ScorePoint {
  date: string
  score: number
  documents: number
}

export function loadHistory(): DealAnalysis[] {
  try {
    const raw = window.localStorage.getItem(KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveAnalysis(analysis: DealAnalysis): DealAnalysis[] {
  const next = [analysis, ...loadHistory().filter((a) => a.id !== analysis.id)].slice(0, MAX_SAVED)
  persist(next)
  return next
}

export function removeAnalysis(id: string): DealAnalysis[] {
  const next = loadHistory().filter((a) => a.id !== id)
  persist(next)
  return next
}

function persist(list: DealAnalysis[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list))
  } catch {
    // Storage full or blocked: drop the oldest half and try once more.
    try {
      window.localStorage.setItem(KEY, JSON.stringify(list.slice(0, Math.ceil(list.length / 2))))
    } catch {
      // Private mode or blocked storage — history just won't persist.
    }
  }
}

// Every saved run of the same deal name, oldest first, for the score history chart.
export function scoreHistory(deal: DealAnalysis, history: DealAnalysis[]): ScorePoint[] {
  const runs = deal.isSample
    ? [deal]
    : history.filter((a) => a.dealName.trim().toLowerCase() === deal.dealName.trim().toLowerCase())
  const points = (runs.length ? runs : [deal]).map((a) => ({
    date: a.submittedAt,
    score: a.score,
    documents: a.documents.filter((d) => d.status === 'PROCESSED').length,
  }))
  return points.sort((a, b) => a.date.localeCompare(b.date))
}
