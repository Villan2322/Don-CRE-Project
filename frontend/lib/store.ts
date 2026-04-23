/**
 * Simple in-memory store for documents and deal results.
 * In production this would be a real database.
 * Attached to the global object so it survives Next.js hot reloads in dev.
 */

import type { Document, AnalysisResult } from './api'

interface Store {
  documents: Map<string, Document & { content: string }>
  deals: Map<string, AnalysisResult>
}

declare global {
  // eslint-disable-next-line no-var
  var __creStore: Store | undefined
}

if (!global.__creStore) {
  global.__creStore = {
    documents: new Map(),
    deals: new Map(),
  }
}

export const store = global.__creStore
