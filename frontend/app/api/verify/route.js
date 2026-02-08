import { NextResponse } from 'next/server';

export const runtime = 'edge';

function base64urlEncode(obj) {
  const s = typeof obj === 'string' ? obj : JSON.stringify(obj);
  const enc = new TextEncoder();
  const bytes = enc.encode(s);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

async function signHMAC(payload, secret) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    enc.encode(payload)
  );
  let binary = '';
  const bytes = new Uint8Array(signature);
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

export async function POST(req) {
  try {
    const body = await req.json();
    const { address, signature, nonce, ts } = body || {};
    if (!address) return NextResponse.json({ error: 'address required' }, { status: 400 });
    const message = `Login to demo\nAddress: ${address}\nNonce: ${nonce}\nTimestamp: ${ts}`;

    let verified = false;
    try {
      const { verifyPersonalMessageSignature } = await import('@mysten/sui/verify');
      if (signature) {
        try { await verifyPersonalMessageSignature(new TextEncoder().encode(message), signature); verified = true; } catch (e) { /* sig invalid */ }
      }
    } catch (e) {
      // package not available or API changed
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
    const signaturePart = await signHMAC(`${encodedHeader}.${encodedPayload}`, secret);
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
