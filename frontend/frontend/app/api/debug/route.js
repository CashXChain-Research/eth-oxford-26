import { NextResponse } from 'next/server';

export async function POST(req) {
  try {
    const txt = await req.text();
    return NextResponse.json({ received: txt });
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
