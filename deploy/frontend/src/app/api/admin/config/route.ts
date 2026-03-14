/**
 * Next.js API proxy for admin config endpoints.
 * Proxies GET/POST /api/admin/config → backend /api/v1/admin/config
 * Avoids cross-origin CORS issues from the browser.
 */
import { NextRequest, NextResponse } from 'next/server';

const BACKEND_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function proxyRequest(req: NextRequest, method: 'GET' | 'POST') {
  const backendUrl = `${BACKEND_URL}/api/v1/admin/config`;
  const cookieHeader = req.headers.get('cookie') || '';

  const fetchOptions: RequestInit = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Cookie': cookieHeader,
    },
  };

  if (method === 'POST') {
    fetchOptions.body = await req.text();
  }

  try {
    const backendRes = await fetch(backendUrl, fetchOptions);
    const data = await backendRes.json();
    const responseInit: ResponseInit = { status: backendRes.status };
    // Forward set-cookie if present
    const setCookie = backendRes.headers.get('set-cookie');
    if (setCookie) {
      responseInit.headers = { 'Set-Cookie': setCookie };
    }
    return NextResponse.json(data, responseInit);
  } catch (error: any) {
    console.error('[Proxy /api/admin/config]', error?.message || error);
    return NextResponse.json(
      { detail: `Backend unreachable: ${error?.message || 'Unknown error'}` },
      { status: 503 }
    );
  }
}

export async function GET(req: NextRequest) {
  return proxyRequest(req, 'GET');
}

export async function POST(req: NextRequest) {
  return proxyRequest(req, 'POST');
}
