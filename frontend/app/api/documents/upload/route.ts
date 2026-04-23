import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { store } from '@/lib/store'
import type { StoredDocument } from '@/lib/store'
import { extractJSON } from '@/lib/ai-client'

// pdf-parse must be required (CommonJS), not ESM imported
// eslint-disable-next-line @typescript-eslint/no-require-imports
const pdfParse = require('pdf-parse')

const DOCUMENT_TYPES = [
  'lease',
  'rent_roll',
  'boma_measurement',
  'operating_statement',
  'ar_aging',
  'cam_reconciliation',
  'estoppel',
  'other',
] as const

type DocumentType = (typeof DOCUMENT_TYPES)[number]

// PDFs with fewer than this many characters are almost certainly image-only or encrypted.
const MIN_USEFUL_CHARS = 100

function guessTypeFromFilename(filename: string): DocumentType {
  const name = filename.toLowerCase()
  if (name.includes('rent') || name.includes('roll'))   return 'rent_roll'
  if (name.includes('boma') || name.includes('measur')) return 'boma_measurement'
  if (name.includes('lease') || name.includes('tenancy')) return 'lease'
  if (name.includes('cam')  || name.includes('recon'))  return 'cam_reconciliation'
  if (name.includes('ar')   || name.includes('aging'))  return 'ar_aging'
  if (name.includes('operating') || name.includes('p&l') || name.includes('income')) return 'operating_statement'
  return 'other'
}

async function classifyDocument(filename: string, snippet: string): Promise<DocumentType> {
  try {
    const result = await extractJSON<{ document_type: string }>(
      `You are a commercial real estate document classifier.
Given a filename and the first 500 characters of a document, classify it into exactly one of these types:
lease, rent_roll, boma_measurement, operating_statement, ar_aging, cam_reconciliation, estoppel, other.
Return ONLY valid JSON: {"document_type": "<type>"}`,
      `Filename: ${filename}\n\nContent preview:\n${snippet.slice(0, 500)}`,
    )
    const t = result.document_type?.toLowerCase() as DocumentType
    return DOCUMENT_TYPES.includes(t) ? t : guessTypeFromFilename(filename)
  } catch {
    return guessTypeFromFilename(filename)
  }
}

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()
    const file = formData.get('file') as File | null

    if (!file) {
      return NextResponse.json({ detail: 'No file provided' }, { status: 400 })
    }

    console.log('[v0] upload: received', file.name, file.size, 'bytes, mime:', file.type)

    const bytes = await file.arrayBuffer()
    const buffer = Buffer.from(bytes)

    // ── Text extraction ────────────────────────────────────────────────────────
    let textContent = ''
    let extractionFailed = false
    let extractionError: string | undefined

    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')
    const isSpreadsheet = /\.(xlsx|xls|csv)$/i.test(file.name)

    if (isPdf) {
      try {
        const parsed = await pdfParse(buffer)
        textContent = (parsed.text ?? '').trim()
        console.log('[v0] upload: pdf-parse extracted', textContent.length, 'chars,', parsed.numpages, 'pages')

        if (textContent.length < MIN_USEFUL_CHARS) {
          extractionFailed = true
          extractionError = `Only ${textContent.length} characters extracted — this PDF appears to be image-only or encrypted. Provide a text-based or OCR-processed PDF.`
          console.warn('[v0] upload: below MIN_USEFUL_CHARS:', extractionError)
        }
      } catch (err: unknown) {
        extractionFailed = true
        extractionError = err instanceof Error ? err.message : 'pdf-parse failed with unknown error'
        textContent = ''
        console.error('[v0] upload: pdf-parse threw:', extractionError)
      }
    } else if (isSpreadsheet) {
      // Placeholder — xlsx parsing would go here
      textContent = `[Spreadsheet: ${file.name} (${file.size} bytes) — text extraction not yet implemented for spreadsheets]`
      console.log('[v0] upload: spreadsheet stored as placeholder')
    } else {
      try {
        textContent = new TextDecoder('utf-8', { fatal: true }).decode(buffer)
        console.log('[v0] upload: plain text read', textContent.length, 'chars')
      } catch {
        textContent = ''
        extractionFailed = true
        extractionError = 'File could not be decoded as UTF-8 text'
      }
    }

    // ── Classify (always — filename gives a hint even if extraction failed) ────
    const documentType = await classifyDocument(file.name, textContent)
    console.log('[v0] upload: classified as', documentType)

    // ── Store ──────────────────────────────────────────────────────────────────
    const documentId = randomUUID()
    const now = new Date().toISOString()

    const doc: StoredDocument = {
      id: documentId,
      filename: file.name,
      document_type: documentType,
      status: extractionFailed ? 'error' : 'completed',
      uploaded_at: now,
      processed_at: now,
      page_count: null,
      extracted_data: null,
      content: textContent,
      charCount: textContent.length,
      extractionFailed,
      extractionError,
    }

    store.documents.set(documentId, doc)
    console.log('[v0] upload: stored', documentId, '— store size:', store.documents.size)

    // ── Response ───────────────────────────────────────────────────────────────
    return NextResponse.json({
      message: `Document '${file.name}' uploaded and classified as ${documentType}`,
      document_id: documentId,
      document_type: documentType,
      status: extractionFailed ? 'error' : 'completed',
      char_count: textContent.length,
      extraction_failed: extractionFailed,
      extraction_error: extractionError ?? null,
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Upload failed'
    console.error('[v0] upload error:', message)
    return NextResponse.json({ detail: message }, { status: 500 })
  }
}
