import { NextRequest, NextResponse } from 'next/server'

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

function getHeaders(req: NextRequest): HeadersInit {
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  const cookie = req.headers.get('cookie')
  if (cookie) headers['Cookie'] = cookie
  const auth = req.headers.get('authorization')
  if (auth) headers['Authorization'] = auth
  return headers
}

export async function GET(req: NextRequest) {
  try {
    const res = await fetch(BACKEND_URL + '/api/v1/admin/config', {
      method: 'GET',
      headers: getHeaders(req),
      cache: 'no-store',
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error'
    return NextResponse.json({ detail: 'Proxy error: ' + msg }, { status: 502 })
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json()
    const res = await fetch(BACKEND_URL + '/api/v1/admin/config', {
      method: 'POST',
      headers: getHeaders(req),
      body: JSON.stringify(body),
      cache: 'no-store',
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error'
    return NextResponse.json({ detail: 'Proxy error: ' + msg }, { status: 502 })
  }
}
