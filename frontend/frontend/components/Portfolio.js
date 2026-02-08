"use client";
import React, { useEffect, useState } from "react";

export default function Portfolio({ address, wallet, network = "testnet", demo = false }) {
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState([]);
  const [error, setError] = useState(null);
  const [prices, setPrices] = useState({});
  const [totalFiat, setTotalFiat] = useState(null);

  const rpc = network === "mainnet"
    ? "https://fullnode.mainnet.sui.io:443"
    : "https://fullnode.testnet.sui.io:443";

  useEffect(() => {
    if (!address && !demo) return;
    let cancelled = false;

    // If demo mode requested, show static demo entries (use numeric balances)
    if (demo) {
      setLoading(false);
      setError(null);
      setEntries([
        { coinType: 'SUI', balance: 123.456, objectId: 'demo-sui' },
        { coinType: 'USDC', balance: 1000.0, objectId: 'demo-usdc' },
        { coinType: 'BTC', balance: 0.0123, objectId: 'demo-btc' },
      ]);
      return () => { cancelled = true; };
    }

    async function fetchPortfolio() {
      setLoading(true);
      setError(null);
      try {
        // 1) If the injected wallet exposes a balance helper, prefer it
        if (wallet && (wallet.getBalances || wallet.getCoinBalances)) {
          try {
            const balances = wallet.getBalances
              ? await wallet.getBalances(address)
              : await wallet.getCoinBalances(address);
            if (!cancelled) setEntries(balances || []);
            setLoading(false);
            return;
          } catch (e) {
            // fallthrough to RPC approach
          }
        }

        // 2) Fallback: query fullnode RPC for objects owned by address
        const resp = await fetch(rpc, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "sui_getObjectsOwnedByAddress", params: [address] }),
        });
        const j = await resp.json();
        const objs = (j.result || []).map((o) => o.objectId || o.object_id || o);

        const seen = [];
        const coins = [];

        // Limit requests to avoid long loads
        for (const id of objs.slice(0, 60)) {
          try {
            const r2 = await fetch(rpc, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "sui_getObject", params: [id] }),
            });
            const j2 = await r2.json();
            const obj = j2.result;
            if (!obj || !obj.data) continue;

            const type = obj.data.type || obj.data.content?.type || "unknown";

            // Heuristic: coin objects include '::coin::Coin<' in their type
            if (typeof type === "string" && type.includes("::coin::Coin<")) {
              // try to extract balance from fields
              let balance = null;
              if (obj.data.fields && obj.data.fields.balance != null) balance = obj.data.fields.balance;
              else if (obj.data.content && obj.data.content.fields && obj.data.content.fields.balance != null)
                balance = obj.data.content.fields.balance;

              const coinTypeMatch = type.match(/Coin<(.+)>/);
              const coinType = coinTypeMatch ? coinTypeMatch[1] : type;
              if (!seen.includes(coinType)) {
                seen.push(coinType);
                coins.push({ coinType, balance: balance != null ? String(balance) : "unknown", objectId: id });
              }
            }
          } catch (e) {
            // ignore per-object errors
          }
        }

        if (!cancelled) setEntries(coins.map(c => ({ ...c, balance: c.balance === 'unknown' ? null : (isNaN(Number(c.balance)) ? c.balance : Number(c.balance)) })));
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    fetchPortfolio();
    return () => { cancelled = true; };
  }, [address, wallet, rpc]);

  // Fetch fiat prices for known coin types and compute total fiat value
  useEffect(() => {
    if (!entries || entries.length === 0) {
      setPrices({});
      setTotalFiat(null);
      return;
    }

    let cancelled = false;
    async function loadPrices() {
      // Map coinType heuristics to CoinGecko ids
      const map = {
        'SUI': 'sui',
        'USDC': 'usd-coin',
        'BTC': 'bitcoin',
        'ETH': 'ethereum'
      };
      const ids = entries.map(e => {
        // try to extract known token part
        const key = Object.keys(map).find(k => e.coinType && e.coinType.toUpperCase().includes(k));
        return key ? map[key] : null;
      }).filter(Boolean);

      if (ids.length === 0) {
        setPrices({});
        setTotalFiat(null);
        return;
      }

      try {
        const url = `https://api.coingecko.com/api/v3/simple/price?ids=${Array.from(new Set(ids)).join(',')}&vs_currencies=usd`;
        const r = await fetch(url);
        const j = await r.json();
        if (cancelled) return;
        setPrices(j || {});

        // compute total
        let total = 0;
        for (const e of entries) {
          const key = Object.keys(map).find(k => e.coinType && e.coinType.toUpperCase().includes(k));
          const id = key ? map[key] : null;
          const bal = typeof e.balance === 'number' ? e.balance : (typeof e.balance === 'string' ? Number(e.balance.replace(/[, ]+/g, '')) : null);
          if (id && bal != null && j[id] && j[id].usd != null) {
            total += bal * j[id].usd;
          }
        }
        setTotalFiat(Number.isFinite(total) ? total : null);
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    }

    loadPrices();
    return () => { cancelled = true; };
  }, [entries]);

  return (
    <div style={{ marginTop: 12, padding: 12, border: '1px solid #eee', borderRadius: 8 }}>
      <div style={{ fontWeight: 600, marginBottom: 8 }}>Live Portfolio</div>
      {totalFiat != null && (
        <div style={{ marginBottom: 8, color: '#0b74de', fontWeight: 600 }}>Total (USD): ${totalFiat.toLocaleString(undefined, { maximumFractionDigits: 2 })}</div>
      )}
      {!address && <div style={{ color: '#666' }}>Connect a wallet to view on-chain portfolio.</div>}
      {address && loading && <div style={{ color: '#666' }}>Loading portfolio…</div>}
      {address && error && <div style={{ color: 'crimson' }}>Error: {error}</div>}
      {address && !loading && entries && entries.length === 0 && <div style={{ color: '#666' }}>No coin-like objects found (or still loading).</div>}
      {entries && entries.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {entries.map((e) => (
            <div key={e.objectId} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <div style={{ color: '#111' }}>{e.coinType}</div>
              <div style={{ color: '#333', fontVariantNumeric: 'tabular-nums' }}>
                {typeof e.balance === 'number' ? e.balance.toLocaleString(undefined, { maximumFractionDigits: 6 }) : e.balance}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
