import { NextRequest, NextResponse } from 'next/server'
import { store } from '@/lib/store'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ dealId: string }> },
) {
  const { dealId } = await params
  const result = store.deals.get(dealId)

  if (!result) {
    return NextResponse.json({ detail: 'Deal analysis not found' }, { status: 404 })
  }

  return NextResponse.json(result)
}
