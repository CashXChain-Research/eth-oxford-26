"use client";
import React, { useState } from "react";
import Portfolio from "./Portfolio";

export default function WalletConnector({ onConnect }) {
  const [address, setAddress] = useState(null);
  const [connected, setConnected] = useState(false);
  const [auth, setAuth] = useState(null);
  const [walletObj, setWalletObj] = useState(null);
  const [demo, setDemo] = useState(false);
  const [serverAuth, setServerAuth] = useState(null);
  const [signing, setSigning] = useState(false);

  async function connect() {
    try {
      const maybeWallet = typeof window !== 'undefined' && (window.sui || window.suiWallet || window.suiwallet);
      if (maybeWallet && maybeWallet.connect) {
        await maybeWallet.connect();
        const accounts = maybeWallet.accounts || (maybeWallet.getAccounts ? await maybeWallet.getAccounts() : null);
        const addr = accounts && accounts[0] ? accounts[0].address || accounts[0] : (maybeWallet.address || null);
        setAddress(addr);
        setConnected(true);
        setWalletObj(maybeWallet);
        setDemo(false);

        // restore saved auth if present
        try {
          const saved = localStorage.getItem('walletAuth');
          if (saved) {
            const parsed = JSON.parse(saved);
            if (parsed && parsed.address === addr) {
              setAuth(parsed);
              onConnect && onConnect({ wallet: maybeWallet, address: addr, auth: parsed });
              return;
            }
          }
        } catch (e) {
          // ignore
        }

        onConnect && onConnect({ wallet: maybeWallet, address: addr });

        // auto sign-in if wallet supports signing
        try {
          const canSign = maybeWallet.signMessage || (maybeWallet.signer && maybeWallet.signer.signMessage) || maybeWallet.request;
          if (canSign) {
            setSigning(true);
            try { await login(addr, maybeWallet); } finally { setSigning(false); }
          }
        } catch (e) {
          setSigning(false);
        }

        return;
      }

      // fallback mock address
      const mock = '0x' + Math.floor(Math.random() * 1e16).toString(16);
      setAddress(mock);
      setConnected(true);
      setWalletObj(null);
      setDemo(false);
      onConnect && onConnect({ wallet: null, address: mock, mock: true });
    } catch (e) {
      console.error('Wallet connect failed', e);
      const mock = '0x' + Math.floor(Math.random() * 1e16).toString(16);
      setAddress(mock);
      setConnected(true);
      onConnect && onConnect({ wallet: null, address: mock, mock: true });
    }
  }

  function disconnect() {
    setConnected(false);
    setAddress(null);
    setAuth(null);
    setWalletObj(null);
    setDemo(false);
    setServerAuth(null);
    try { localStorage.removeItem('walletAuth'); } catch (e) {}
    onConnect && onConnect(null);
  }

  async function login(providedAddr, providedWallet) {
    setSigning(true);
    try {
      const maybeWallet = providedWallet || walletObj || (typeof window !== 'undefined' && (window.sui || window.suiWallet || window.suiwallet));
      const addr = providedAddr || address;
      if (!maybeWallet) throw new Error('No wallet');

      const nonce = Math.floor(Math.random() * 1e9).toString(16);
      const ts = Date.now();
      const message = `Login to CashXChain demo\nAddress: ${addr}\nNonce: ${nonce}\nTimestamp: ${ts}`;

      let signature = null;
      if (maybeWallet.signMessage) {
        try { signature = await maybeWallet.signMessage(message); } catch (e) { signature = await maybeWallet.signMessage({ message }); }
      } else if (maybeWallet.signer && maybeWallet.signer.signMessage) {
        signature = await maybeWallet.signer.signMessage(message);
      } else if (maybeWallet.request) {
        try { signature = await maybeWallet.request({ method: 'personal_sign', params: [message, addr] }); } catch (e) {}
      }

      function normalizeSig(sig) {
        if (!sig) return null;
        if (typeof sig === 'string') return sig;
        if (sig && typeof sig === 'object') {
          if (sig.signature) sig = sig.signature;
          else if (sig.sig) sig = sig.sig;
        }
        if (sig instanceof Uint8Array) return Array.from(sig).map(b => b.toString(16).padStart(2, '0')).join('');
        try { return JSON.stringify(sig); } catch (e) { return String(sig); }
      }

      const normalized = normalizeSig(signature);
      const authObj = { address: addr, signature: normalized || null, nonce, ts };
      try { localStorage.setItem('walletAuth', JSON.stringify(authObj)); } catch (e) {}
      setAuth(authObj);
      onConnect && onConnect({ wallet: maybeWallet, address: addr, auth: authObj });

      try {
        const resp = await fetch('/api/verify', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(authObj) });
        const jr = await resp.json();
        setServerAuth(jr);
      } catch (e) {
        setServerAuth({ error: String(e) });
      }
    } catch (e) {
      console.warn('Login (sign) failed', e);
      const authObj = { address: providedAddr || address, signature: null, nonce: null, ts: Date.now() };
      try { localStorage.setItem('walletAuth', JSON.stringify(authObj)); } catch (e) {}
      setAuth(authObj);
      onConnect && onConnect({ wallet: null, address: providedAddr || address, auth: authObj });
    } finally {
      setSigning(false);
    }
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ fontSize: 13, color: '#222' }}>
          Wallet: {connected ? (address || 'connected') : 'not connected'}
          {auth ? (<> — Logged in</>) : connected ? (<> — Not logged in</>) : null}
        </div>
        {!connected ? (
          <button onClick={connect} disabled={signing} style={{ padding: '6px 10px', borderRadius: 6, background: signing ? '#94a3b8' : '#0b74de', color: '#fff', border: 'none' }}>{signing ? 'Connecting…' : 'Connect'}</button>
        ) : (
          <>
            {!auth && (
              <button onClick={() => login()} disabled={signing} style={{ padding: '6px 10px', borderRadius: 6, background: signing ? '#94a3b8' : '#10b981', color: '#fff', border: 'none' }}>{signing ? 'Signing…' : 'Sign in'}</button>
            )}
            <button onClick={disconnect} style={{ padding: '6px 10px', borderRadius: 6, background: '#d93b3b', color: '#fff', border: 'none' }}>Disconnect</button>
          </>
        )}
      </div>

      {auth && (
        <div style={{ marginTop: 8, fontSize: 12, color: '#444' }}>
          <div>Address: {auth.address}</div>
          <div>Signature: {auth.signature ? (<span style={{ wordBreak: 'break-all' }}>{auth.signature}</span>) : 'none (demo)'}</div>
        </div>
      )}

      {serverAuth && (
        <div style={{ marginTop: 8, fontSize: 12, color: serverAuth.error ? 'crimson' : '#0b74de' }}>
          {serverAuth.error ? `Server verify error: ${serverAuth.error}` : `Server: ${serverAuth.message || JSON.stringify(serverAuth)}`}
        </div>
      )}

      <div style={{ marginTop: 10 }}>
        {!connected && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setDemo(true)} style={{ padding: '6px 10px', borderRadius: 6, background: '#6b7280', color: '#fff', border: 'none' }}>View demo portfolio</button>
          </div>
        )}
        {connected && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={() => setDemo((s) => !s)} style={{ padding: '6px 10px', borderRadius: 6, background: '#f59e0b', color: '#fff', border: 'none' }}>{demo ? 'Hide demo' : 'Show demo'}</button>
          </div>
        )}
      </div>

      {(connected || demo) && (
        <Portfolio address={address} wallet={walletObj} demo={demo} />
      )}
    </div>
  );
}
