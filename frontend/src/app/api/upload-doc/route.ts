import { NextRequest, NextResponse } from 'next/server';

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const backendUrl = `${apiBase}/api/v1/search/extract-and-describe`;

    const backendRes = await fetch(backendUrl, {
      method: 'POST',
      body: formData,
    });

    const contentType = backendRes.headers.get('content-type') || '';
    if (!backendRes.ok) {
      let detail = 'Failed to analyze documents';
      if (contentType.includes('application/json')) {
        const errData = await backendRes.json().catch(() => ({}));
        detail = errData.detail || detail;
      }
      return NextResponse.json({ detail }, { status: backendRes.status });
    }

    const data = await backendRes.json();
    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Proxy error';
    return NextResponse.json({ detail: message }, { status: 500 });
  }
}
