"use client";
import React, { useState } from 'react';

const AI_ENDPOINT = 'https://cashxchain-ai-v1.cashxchain.workers.dev/';

export default function MarketAgentConsole() {
  const [prompt, setPrompt] = useState('');
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [agentName] = useState('MarketQuantumExecutor');

  function shorten(text) {
    if (!text) return '';
    const s = String(text).trim();
    const para = s.split(/\n\s*\n/)[0];
    const sentences = para.match(/[^.!?]+[.!?]?/g) || [para];
    const short = sentences.slice(0, 2).join(' ').trim();
    // if short ends without terminal punctuation, try to extend to next sentence
    if (short && !/[.!?]$/.test(short) && sentences.length > 2) {
      return (sentences.slice(0, 3).join(' ')).trim();
    }
    return short;
  }

  async function send() {
    if (!prompt.trim()) return;
    const userMsg = { role: 'user', text: prompt };
    setMessages((m) => [...m, userMsg]);
    setLoading(true);
    try {
      const systemPrefix = `You are ${agentName}. Answer concisely and directly. Use at most 2 sentences or 3 bullet points. No extra commentary.`;
      const fullPrompt = `${systemPrefix}\n\n${prompt}`;
      const body = { prompt: fullPrompt, recipient: agentName, temperature: 0.05, max_tokens: 150 };
      const r = await fetch(AI_ENDPOINT, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      const raw = j && (j.result?.response || j.choices?.[0]?.text || j.text || j.reply || JSON.stringify(j));
      const preview = shorten(raw);
      const botMsg = { role: 'agent', text: preview || raw.slice(0, 200), fullText: String(raw || ''), expanded: false };
      setMessages((m) => [...m, botMsg]);
    } catch (e) {
      setMessages((m) => [...m, { role: 'agent', text: `Error: ${String(e)}` }]);
    } finally {
      setLoading(false);
      setPrompt('');
    }
  }

  function quickPreset(p) {
    setPrompt(p);
  }

  return (
    <div style={{ marginTop: 18, padding: 12, borderRadius: 8, background: 'rgba(255,255,255,0.95)', color: '#000' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontWeight: 700 }}>Market Quantum Execution — Agent Console</div>
        <div style={{ fontSize: 12, color: '#666' }}>Agent: {agentName}</div>
      </div>

      <div style={{ marginTop: 8, display: 'flex', gap: 8 }}>
        <button onClick={() => quickPreset('Simulate market buy of 100 SUI at market price; output steps and estimated cost')} style={{ padding: '6px 8px', borderRadius: 6 }}>Buy 100 SUI</button>
        <button onClick={() => quickPreset('Simulate market sell of 0.5 BTC wrapped; show slippage and gas estimate')} style={{ padding: '6px 8px', borderRadius: 6 }}>Sell 0.5 BTC</button>
        <button onClick={() => quickPreset('Provide a risk assessment for executing a 10k USDC swap on Sui testnet with available liquidity')} style={{ padding: '6px 8px', borderRadius: 6 }}>Risk</button>
      </div>

      <div style={{ marginTop: 10 }}>
        <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Type a market execution or strategy prompt..." style={{ width: '100%', minHeight: 72, padding: 8 }} />
        <div style={{ marginTop: 8, display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={() => { setPrompt(''); setMessages([]); }} style={{ padding: '6px 10px', borderRadius: 6, background: '#9ca3af', color: '#fff', border: 'none' }}>Clear</button>
          <button onClick={send} disabled={loading} style={{ padding: '6px 10px', borderRadius: 6, background: '#0b74de', color: '#fff', border: 'none' }}>{loading ? 'Sending…' : 'Send'}</button>
        </div>
      </div>

      <div style={{ marginTop: 12, maxHeight: 220, overflow: 'auto', borderTop: '1px solid #eee', paddingTop: 8 }}>
        {messages.map((m, i) => (
          <div key={i} style={{ marginBottom: 8 }}>
            <div style={{ fontSize: 12, color: m.role === 'user' ? '#111' : '#0b74de', fontWeight: 600 }}>{m.role === 'user' ? 'You' : agentName}</div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
              <div style={{ flex: 1 }}>
                <div style={{ whiteSpace: 'pre-wrap', background: m.role === 'user' ? '#f8fafc' : '#eef2ff', padding: 8, borderRadius: 6 }}>{m.role === 'agent' && m.fullText && !m.expanded ? (m.text || m.fullText.slice(0, 200) + '...') : (m.fullText || m.text)}</div>
              </div>
              {m.role === 'agent' && m.fullText && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <button onClick={() => {
                    setMessages(ms => ms.map((mm, idx) => idx === i ? { ...mm, expanded: !mm.expanded } : mm));
                  }} style={{ padding: '6px 8px', borderRadius: 6, background: '#e6edf3', border: 'none', cursor: 'pointer' }}>{m.expanded ? 'Show less' : 'Show more'}</button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
