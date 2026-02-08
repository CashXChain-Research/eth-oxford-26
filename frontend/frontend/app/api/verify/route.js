import { NextResponse } from 'next/server';
import crypto from 'crypto';

function base64urlEncode(obj) {
  const s = typeof obj === 'string' ? obj : JSON.stringify(obj);
  return Buffer.from(s).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function signHMAC(payload, secret) {
  return crypto.createHmac('sha256', secret).update(payload).digest('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function POST(req) {
  try {
    const body = await req.json();
    const { address, signature, nonce, ts } = body || {};
    if (!address) return NextResponse.json({ error: 'address required' }, { status: 400 });
    const message = `Login to demo\nAddress: ${address}\nNonce: ${nonce}\nTimestamp: ${ts}`;

    let verified = false;
    try {
      const sui = await import('@mysten/sui.js');
      if (sui && typeof sui.verifyMessage === 'function') {
        try { verified = await sui.verifyMessage(message, signature, address); } catch (e) { /* ignore */ }
      }
    } catch (e) {
      // package not available
    }

    // demo fallback: accept non-empty signature
    if (!verified && signature) verified = true;

    if (!verified) return NextResponse.json({ ok: false, error: 'invalid signature' }, { status: 401 });

    // create a simple JWT (HS256)
    const secret = process.env.JWT_SECRET || 'dev-secret-change-this';
    const iat = Math.floor(Date.now() / 1000);
    const exp = iat + (60 * 60); // 1h
    const payload = { sub: address, iat, exp };
    const header = { alg: 'HS256', typ: 'JWT' };
    const encodedHeader = base64urlEncode(header);
    const encodedPayload = base64urlEncode(payload);
    const signaturePart = signHMAC(`${encodedHeader}.${encodedPayload}`, secret);
    const token = `${encodedHeader}.${encodedPayload}.${signaturePart}`;

    const res = NextResponse.json({ ok: true, message: 'verified', token }, { status: 200 });
    // set cookie (HttpOnly)
    const maxAge = 60 * 60; // 1h
    res.headers.set('Set-Cookie', `session=${token}; HttpOnly; Path=/; Max-Age=${maxAge}`);
    return res;
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 500 });
  }
}
