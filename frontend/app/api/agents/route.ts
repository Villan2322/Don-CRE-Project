import { NextResponse } from 'next/server'
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000'
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/agents`)
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch {
    return NextResponse.json({ error: 'Backend unavailable' }, { status: 502 })
  }
}
