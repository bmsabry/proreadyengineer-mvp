// Proxy disabled - admin settings page calls backend directly
// Direct calls preserve auth cookies and avoid cross-domain issues
import { NextResponse } from 'next/server';
export async function GET() {
  return NextResponse.json({ detail: 'Use direct backend API' }, { status: 410 });
}
export async function POST() {
  return NextResponse.json({ detail: 'Use direct backend API' }, { status: 410 });
}
