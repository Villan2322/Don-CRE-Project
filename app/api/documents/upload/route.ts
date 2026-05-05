import { NextRequest, NextResponse } from 'next/server'

// Document type classification based on filename patterns
function classifyDocument(filename: string): string {
  const lowerName = filename.toLowerCase()
  
  if (lowerName.includes('rent roll') || lowerName.includes('rentroll')) {
    return 'Rent Roll'
  }
  if (lowerName.includes('lease') || lowerName.includes('executed')) {
    return 'Lease Agreement'
  }
  if (lowerName.includes('boma') || lowerName.includes('measurement')) {
    return 'BOMA Measurement'
  }
  if (lowerName.includes('operating') || lowerName.includes('income') || lowerName.includes('expense')) {
    return 'Operating Statement'
  }
  if (lowerName.includes('aging') || lowerName.includes('ar ')) {
    return 'AR Aging Report'
  }
  if (lowerName.includes('cam') || lowerName.includes('reconciliation')) {
    return 'CAM Reconciliation'
  }
  if (lowerName.includes('t-12') || lowerName.includes('t12')) {
    return 'T-12 Statement'
  }
  if (lowerName.includes('estoppel')) {
    return 'Tenant Estoppel'
  }
  
  // Default classification based on file type
  if (lowerName.endsWith('.pdf')) {
    return 'PDF Document'
  }
  if (lowerName.endsWith('.xlsx') || lowerName.endsWith('.xls') || lowerName.endsWith('.csv')) {
    return 'Spreadsheet'
  }
  
  return 'Unknown Document'
}

export async function POST(request: NextRequest) {
  try {
    const formData = await request.formData()
    const file = formData.get('file') as File | null

    if (!file) {
      return NextResponse.json(
        { error: 'No file provided' },
        { status: 400 }
      )
    }

    // Validate file type
    const allowedTypes = [
      'application/pdf',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-excel',
      'text/csv',
    ]

    if (!allowedTypes.includes(file.type) && !file.name.match(/\.(pdf|xlsx|xls|csv)$/i)) {
      return NextResponse.json(
        { error: 'Invalid file type. Supported formats: PDF, XLSX, XLS, CSV' },
        { status: 400 }
      )
    }

    // Classify the document
    const documentType = classifyDocument(file.name)

    // In production, this would:
    // 1. Upload to blob storage (Vercel Blob, S3, etc.)
    // 2. Store metadata in database
    // 3. Queue for AI processing

    // For now, return success with classification
    const documentId = crypto.randomUUID()

    return NextResponse.json({
      success: true,
      documentId,
      filename: file.name,
      size: file.size,
      type: file.type,
      message: `Document uploaded and classified as ${documentType}`,
      classification: documentType,
    })
  } catch (error) {
    console.error('Upload error:', error)
    return NextResponse.json(
      { error: 'Failed to process upload' },
      { status: 500 }
    )
  }
}
