/**
 * Global in-memory store that survives Next.js HMR and cross-route module
 * boundaries by hanging off globalThis. Each document uploaded is stored here
 * until the process restarts.
 *
 * Self-contained — no imports from other local modules so it can be safely
 * required by any route without circular dependency risk.
 */

export interface StoredDocument {
  id: string
  filename: string
  document_type: string
  status: 'completed' | 'error'
  uploaded_at: string
  processed_at: string
  page_count: number | null
  extracted_data: unknown | null
  /** Full extracted text content */
  content: string
  /** Number of characters successfully extracted */
  charCount: number
  /** True when pdf-parse could not extract usable text */
  extractionFailed: boolean
  /** Human-readable error from pdf-parse if it failed */
  extractionError?: string
}

export interface StoredDeal {
  id: string
  result: unknown
  createdAt: string
}

interface CREStore {
  documents: Map<string, StoredDocument>
  deals: Map<string, StoredDeal>
}

declare global {
  // eslint-disable-next-line no-var
  var __donCREStore: CREStore | undefined
}

if (!globalThis.__donCREStore) {
  globalThis.__donCREStore = {
    documents: new Map<string, StoredDocument>(),
    deals: new Map<string, StoredDeal>(),
  }
}

export const store = globalThis.__donCREStore
