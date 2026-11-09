import { Carry, DealAnalysis } from './types'

export function canAddDocuments(deal: DealAnalysis): boolean {
  return !deal.isSample && !!deal.carry && deal.carry.version === 1
}

// Drops removed documents (by dashboard document id) from what gets sent back.
export function carryWithout(deal: DealAnalysis, removedIds: Set<string>): Carry | undefined {
  const carry = deal.carry
  if (!carry) return undefined
  const removedNames = new Set(deal.documents.filter((d) => removedIds.has(d.id)).map((d) => d.filename))
  const documents = carry.documents.filter((d) => !removedIds.has(d.doc_id))
  const kept = new Set(documents.map((d) => d.doc_id))
  return {
    ...carry,
    documents,
    extractions: carry.extractions.filter((e) => kept.has(e.doc_id)),
    ingest_errors: carry.ingest_errors.filter((e) => !removedNames.has(e.split(': ')[0])),
  }
}
