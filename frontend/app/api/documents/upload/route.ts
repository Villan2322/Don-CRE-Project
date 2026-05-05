import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData()

    const response = await fetch(`${BACKEND_URL}/documents/upload`, {
      method: 'POST',
      body: formData,
    })

    const data = await response.json()

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Upload failed' },
        { status: response.status }
      )
    }

    return NextResponse.json(data)
  } catch (err) {
    console.error('[v0] Upload route error:', err)
    return NextResponse.json(
      { error: 'Backend unavailable. Ensure the FastAPI server is running.' },
      { status: 502 }
    )
  }
}
