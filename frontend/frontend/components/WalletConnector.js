"use client";
import React, { useState } from "react";

export default function WalletConnector({ onConnect }) {
  const [address, setAddress] = useState(null);
  const [connected, setConnected] = useState(false);

  async function connect() {
    try {
      // Try to use a browser-injected Sui wallet
      const maybeWallet = typeof window !== 'undefined' && (window.sui || window.suiWallet || window.suiwallet);
      if (maybeWallet && maybeWallet.connect) {
        await maybeWallet.connect();
        // many Sui wallets expose getAccounts or accounts
        const accounts = maybeWallet.accounts || (maybeWallet.getAccounts ? await maybeWallet.getAccounts() : null);
        const addr = accounts && accounts[0] ? accounts[0].address || accounts[0] : (maybeWallet.address || null);
        setAddress(addr);
        setConnected(true);
        onConnect && onConnect({ wallet: maybeWallet, address: addr });
        return;
      }

      // Fallback: mock a wallet address for demo mode
      const mock = '0x' + Math.floor(Math.random() * 1e16).toString(16);
      setAddress(mock);
      setConnected(true);
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
    onConnect && onConnect(null);
  }

  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ fontSize: 13, color: '#222' }}>
          Wallet: {connected ? (address || 'connected') : 'not connected'}
        </div>
        {!connected ? (
          <button onClick={connect} style={{ padding: '6px 10px', borderRadius: 6, background: '#0b74de', color: '#fff', border: 'none' }}>Connect</button>
        ) : (
          <button onClick={disconnect} style={{ padding: '6px 10px', borderRadius: 6, background: '#d93b3b', color: '#fff', border: 'none' }}>Disconnect</button>
        )}
      </div>
    </div>
  );
}
