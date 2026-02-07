"use client";
import React, { useState, useRef, useEffect } from 'react';

export default function JohannChat() {
  const [messages, setMessages] = useState([
    { from: 'Johann', text: 'Hello — I am Johann. You can write to me here.' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const containerRef = useRef(null);
  // Brief site summary to include with every AI request so Johann can answer
  const SITE_SUMMARY = `This demo site contains three main parts: (1) Quantum RNG UI demonstrating a random number generator component; (2) AI Agents demo where Tom responds to user messages and on-chain event comments; (3) a Sui Escrow demo that simulates (or uses a connected wallet for) simple escrow flows. The demo uses a public AI endpoint for agent replies. This site is created by the CashXChain Research department (Special Thanks to Dosentelefoni).`;
  const JOHANN_PERSONA = `You are Johann, a friendly, informal assistant for demo users. Prefer UI-focused instructions that reference interface elements (e.g. the Quantum RNG "Generate" button). Speak briefly (1-3 sentences), use plain language, include a quick action or example when helpful, and avoid technical jargon and code snippets unless the user explicitly asks for developer instructions.`;
  const JOHANN_EXAMPLES = `Example:
User: How do I generate a random number?
Johann: Click the red "Generate" button in the Quantum RNG section; it shows a demo random number you can copy.`;

  // Do NOT auto-insert the credit message; only provide it to the AI prompt
  // and instruct Johann to reveal authorship only when explicitly asked by the user.

  async function send() {
    if (!input || !input.trim()) return;
    const text = input.trim();
    setMessages((m) => [...m, { from: 'You', text }]);
    setInput('');
    setError(null);
    // Local detection: if the user explicitly asks who made the site, reply locally
    const authorshipPattern = /who (made|created) this site|who made this site|who created this site|wer (hat )?(die|diese) seite (gemacht|erstellt)|wer hat diese seite gemacht|wer hat die seite gemacht/i;
    if (authorshipPattern.test(text)) {
      const isGerman = /wer/i.test(text);
      const credit = isGerman
        ? 'Diese Seite wurde erstellt von CashXChain Research (Special Thanks to Dosentelefoni).'
        : 'This site was created by CashXChain Research (Special Thanks to Dosentelefoni).';
      setMessages((m) => [...m, { from: 'Johann', text: credit }]);
      return;
    }

    // Call the demo AI endpoint for Johann
    setLoading(true);
    try {
      const url = 'https://cashxchain-ai-v1.cashxchain.workers.dev/';
      // Compose a stronger, agent-unique prompt enforcing distinct voice
      const fullPrompt = "AgentName: Johann" + "\n" +
        "Persona: " + JOHANN_PERSONA + "\n" +
        "Distinctness: Do NOT imitate or copy other site agents (e.g. Tom). Use a friendly, informal tone and respond in 1-3 short sentences. Return only the assistant text (no 'Johann:' prefix)." +
        "\n\nSiteContext: " + SITE_SUMMARY + "\n\nExamples:\n" + JOHANN_EXAMPLES + "\nUser: " + text +
        "\n\nInstruction: Answer succinctly. Only reveal site authorship (CashXChain Research, Dosentelefoni) when the user explicitly asks who created or maintains the site (see examples). If unsure, ask for clarification instead of echoing internal site text.";
      // Use a moderate temperature for Johann and prefer UI guidance over code
      const body = { prompt: fullPrompt, recipient: 'Johann', context: SITE_SUMMARY, temperature: 0.6, max_tokens: 300 };

      // retry logic with small backoff
      let resp = null;
      let attempt = 0;
      let txt = '';
      while (attempt < 3) {
        try {
          resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
          if (!resp.ok) throw new Error('AI_ERROR');
          txt = await resp.text();
          break;
        } catch (err) {
          attempt += 1;
          if (attempt >= 3) throw err;
          await new Promise((r) => setTimeout(r, 300 * attempt));
        }
      }
      let data = null;
      try { data = JSON.parse(txt); } catch (e) { data = txt; }
      // Robust extraction of reply from various response shapes
      let reply = '';
      if (typeof data === 'string') reply = data;
      else if (data && typeof data === 'object') {
        reply = data.reply || data.response || data.text || (data.result && data.result.response) || '';
        if (!reply) {
          try { reply = JSON.stringify(data); } catch (e) { reply = '' }
        }
      }
      // sanitize and normalize
      if (typeof reply === 'string') {
        reply = reply.trim();
        // remove accidental prefixes like 'Johann:'
        reply = reply.replace(/^Johann:\s*/i, '');
        // clip to reasonable length
        if (reply.length > 2000) reply = reply.slice(0, 2000) + '...';
      }
      // If Johann returned developer-style code or library references, prefer UI guidance instead
      const codePattern = /Math\.random|import\s|random\.|`|console\.log|function\s|randint\(|\bint\b|\bfloat\b/i;
      if (typeof reply === 'string' && codePattern.test(reply)) {
        reply = 'Click the red "Generate" button in the Quantum RNG section to produce a demo random number you can copy.';
      }
      // If the AI accidentally echoed the site summary or credit without an explicit ask, strip it
      if (!authorshipPattern.test(text)) {
        if (typeof reply === 'string' && (reply.includes('This demo site contains') || reply.includes('CashXChain Research') || reply.includes('Dosentelefoni'))) {
          // remove the site summary portion
          reply = reply.replace(/This demo site contains[\s\S]*/i, '').replace(/CashXChain Research\s*\(?Special Thanks to Dosentelefoni\)?/i, '').trim();
        }
        if (!reply || reply.length < 6) reply = 'I can help with that — could you rephrase your question?';
      }
      if (!reply) reply = 'I got your message.';
      setMessages((m) => [...m, { from: 'Johann', text: reply }]);
    } catch (e) {
      console.warn('Johann AI request failed', e);
      setError('Sorry, I cannot reach the AI right now.');
      setMessages((m) => [...m, { from: 'Johann', text: 'Sorry, I cannot reach the AI right now.' }]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // scroll so the bottom is visible plus 30px gap to avoid overlap
    el.scrollTop = el.scrollHeight - el.clientHeight + 30;
  }, [messages]);

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!loading) send();
    }
  }

  return (
    <div style={{ marginTop: 18, padding: 12, background: 'rgba(255,255,255,0.03)', borderRadius: 8 }}>
      <h3 style={{ marginTop: 0, color: '#fff' }}>Chat with Johann</h3>
      <div ref={containerRef} style={{ maxHeight: 280, overflow: 'auto', padding: 12, paddingBottom: 30, boxSizing: 'border-box' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: '8px 0', clear: 'both' }}>
            <div style={{ fontWeight: 700, color: m.from === 'Johann' ? '#6ee7b7' : '#fff', marginBottom: 4 }}>{m.from}:</div>
            <div style={{ color: m.from === 'Johann' ? '#34d399' : '#e5e7eb', background: 'rgba(0,0,0,0.05)', padding: 8, borderRadius: 6, display: 'inline-block', maxWidth: '100%' }}>{m.text}</div>
          </div>
        ))}
      </div>

      <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Write to Johann"
          rows={2}
          style={{ flex: 1, padding: 10, borderRadius: 6, border: '1px solid rgba(255,255,255,0.08)', background: 'transparent', color: '#fff', resize: 'vertical' }}
        />
        <button onClick={send} disabled={loading} style={{ padding: '8px 12px', borderRadius: 6, background: '#10b981', color: '#fff', border: 'none' }}>
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
      {error && <div style={{ marginTop: 8, color: '#fda4af' }}>{error}</div>}
    </div>
  );
}
