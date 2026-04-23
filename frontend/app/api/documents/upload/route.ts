import { NextRequest, NextResponse } from 'next/server'
import { randomUUID } from 'crypto'
import { store } from '@/lib/store'
import { extractJSON } from '@/lib/ai-client'

// pdf-parse needs to be required (CommonJS) not imported
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

async function classifyDocument(
  filename: string,
  textSnippet: string,
): Promise<DocumentType> {
  try {
    const result = await extractJSON<{ document_type: string }>(
      'You are a commercial real estate document classifier. Given a filename and the first 500 characters of a document, classify it into one of these types: lease, rent_roll, boma_measurement, operating_statement, ar_aging, cam_reconciliation, estoppel, other. Return JSON: {"document_type": "<type>"}',
      `Filename: ${filename}\n\nContent preview:\n${textSnippet.slice(0, 500)}`,
    )
    const t = result.document_type?.toLowerCase() as DocumentType
    return DOCUMENT_TYPES.includes(t) ? t : 'other'
  } catch {
    // Fallback: guess from filename
    const name = filename.toLowerCase()
    if (name.includes('rent') || name.includes('roll')) return 'rent_roll'
    if (name.includes('boma') || name.includes('measur')) return 'boma_measurement'
    if (name.includes('lease') || name.includes('tenancy')) return 'lease'
    if (name.includes('cam') || name.includes('recon')) return 'cam_reconciliation'
    if (name.includes('ar') || name.includes('aging')) return 'ar_aging'
    if (name.includes('operating') || name.includes('p&l') || name.includes('income')) return 'operating_statement'
    return 'other'
  }
}

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()
    const file = formData.get('file') as File | null

    if (!file) {
      return NextResponse.json({ detail: 'No file provided' }, { status: 400 })
    }

    const bytes = await file.arrayBuffer()
    const buffer = Buffer.from(bytes)

    // Extract text
    let textContent = ''
    const isPdf =
      file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')

    if (isPdf) {
      try {
        const parsed = await pdfParse(buffer)
        textContent = parsed.text ?? ''
      } catch {
        textContent = `[Could not parse PDF: ${file.name}]`
      }
    } else {
      // For Excel/CSV just record the filename for now
      textContent = `[Spreadsheet: ${file.name}]`
    }

    const documentType = await classifyDocument(file.name, textContent)
    const documentId = randomUUID()
    const now = new Date().toISOString()

    store.documents.set(documentId, {
      id: documentId,
      filename: file.name,
      document_type: documentType,
      status: 'completed',
      uploaded_at: now,
      processed_at: now,
      page_count: null,
      extracted_data: null,
      content: textContent,
    })

    return NextResponse.json({
      message: `Document '${file.name}' uploaded and classified as ${documentType}`,
      document_id: documentId,
      status: 'completed',
    })
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Upload failed'
    console.error('[v0] Upload error:', message)
    return NextResponse.json({ detail: message }, { status: 500 })
  }
}
