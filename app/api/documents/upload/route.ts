import { NextRequest, NextResponse } from 'next/server'

// Document type classification based on filename patterns (fallback for local dev)
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

    // In production (Vercel deployment), call the Python backend
    const isProduction = process.env.VERCEL_ENV === 'production' || process.env.VERCEL_ENV === 'preview'
    
    if (isProduction) {
      try {
        // Forward the file to Python backend
        const backendFormData = new FormData()
        backendFormData.append('file', file)
        
        const backendUrl = process.env.VERCEL_URL 
          ? `https://${process.env.VERCEL_URL}` 
          : ''
        
        const backendResponse = await fetch(`${backendUrl}/backend/documents/upload`, {
          method: 'POST',
          body: backendFormData,
        })
        
        if (backendResponse.ok) {
          const result = await backendResponse.json()
          return NextResponse.json({
            success: true,
            documentId: result.document_id,
            filename: file.name,
            size: file.size,
            type: file.type,
            message: result.message,
            classification: result.status || 'Processing',
            backend: true,
          })
        }
        // Fall through to mock if backend fails
        console.error('Backend upload failed, using mock:', await backendResponse.text())
      } catch (backendError) {
        console.error('Backend connection failed, using mock:', backendError)
      }
    }

    // Fallback: Mock classification for local development or if backend unavailable
    const documentType = classifyDocument(file.name)
    const documentId = crypto.randomUUID()

    return NextResponse.json({
      success: true,
      documentId,
      filename: file.name,
      size: file.size,
      type: file.type,
      message: `Document uploaded and classified as ${documentType}`,
      classification: documentType,
      backend: false,
    })
  } catch (error) {
    console.error('Upload error:', error)
    return NextResponse.json(
      { error: 'Failed to process upload' },
      { status: 500 }
    )
  }
}
