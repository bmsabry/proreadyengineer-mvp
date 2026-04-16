import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

// Server-side proxy for admin config - avoids cross-domain cookie/CORS issues
// This runs on the Next.js server, reads the httpOnly access_token cookie,
// and forwards requests to the backend with Authorization header.
const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function GET(_request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const accessToken = cookieStore.get('access_token')?.value;

    if (!accessToken) {
      return NextResponse.json({ detail: 'Unauthorized - no access token' }, { status: 401 });
    }

    const backendRes = await fetch(`${BACKEND_URL}/api/v1/admin/config`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
    });

    const data = await backendRes.json();
    return NextResponse.json(data, { status: backendRes.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ detail: `Proxy error: ${msg}` }, { status: 500 });
  }
}

export async function POST(request: NextRequest) {
  try {
    const cookieStore = await cookies();
    const accessToken = cookieStore.get('access_token')?.value;

    if (!accessToken) {
      return NextResponse.json({ detail: 'Unauthorized - no access token' }, { status: 401 });
    }

    const body = await request.json();

    const backendRes = await fetch(`${BACKEND_URL}/api/v1/admin/config`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    const data = await backendRes.json();
    return NextResponse.json(data, { status: backendRes.status });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'Unknown error';
    return NextResponse.json({ detail: `Proxy error: ${msg}` }, { status: 500 });
  }
}
