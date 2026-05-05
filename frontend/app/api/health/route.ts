import { NextResponse } from 'next/server'
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/health`)
    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ status: 'backend_unavailable' }, { status: 502 })
  }
}
