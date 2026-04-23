import { NextResponse } from 'next/server'
import { store } from '@/lib/store'

export async function GET() {
  const docs = Array.from(store.documents.values()).map(
    ({ content: _content, ...rest }) => rest,
  )
  return NextResponse.json(docs)
}
