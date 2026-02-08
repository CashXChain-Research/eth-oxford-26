"use client";
import React, { useState, useRef, useEffect } from "react";

export default function AIAgents({ bottomInputs = false, chainEvent = null }) {
  const [messages, setMessages] = useState([
    { from: "Tom", text: "Hello! I'm Tom. How can I help?" },
  ]);
  // include the same site summary/credit so Tom has context about the demo
  const SITE_SUMMARY = `This demo site contains three main parts: (1) Quantum RNG UI demonstrating a random number generator component; (2) AI Agents demo where Tom responds to user messages and on-chain event comments; (3) a Sui Escrow demo that simulates (or uses a connected wallet for) simple escrow flows. The demo uses a public AI endpoint for agent replies. This site is a demo for a quantum portfolio optimizer project.`;
  const TOM_PERSONA = `You are Tom, a technically-focused assistant. Give concise, step-by-step troubleshooting and references to UI elements. Keep tone professional and use precise terminology.`;
  const TOM_EXAMPLES = `Example:\nUser: How do I fund an escrow?\nTom: Use the Sui Escrow UI to create an escrow and then click Fund; if no wallet is connected it simulates funding.`;
  // Make Tom's persona explicitly technical and distinct from Johann
  const TOM_PERSONA_EXPLICIT = `You are Tom, a technically-focused assistant. Provide concise, step-by-step troubleshooting and references to UI elements. Prefer technical explanations and short code examples when helpful; keep tone professional and distinct from other site agents.`;

  // Do NOT auto-insert the credit message for Tom; the SITE_SUMMARY is included
  // in prompts but Tom should reveal authorship only when explicitly asked.
  const [inputTom, setInputTom] = useState("");
  const [loadingTom, setLoadingTom] = useState(false);
  const messagesContainerRef = useRef(null);
  const lastChainEventRef = useRef(null);

  // Return a local time/date response if the user asked for time/date.
  function getLocalTimeResponse(text) {
    if (!text || typeof text !== 'string') return null;
    const t = text.toLowerCase();
    const timePattern = /what time|current time|time now|what's the time|what is the time/;
    const datePattern = /what date|date today|today|what's the date|what is the date/;
    if (timePattern.test(t) || datePattern.test(t)) {
      const now = new Date();
      const date = now.toLocaleDateString('en-US');
      const time = now.toLocaleTimeString('en-US');
      return `Current date: ${date}, Time: ${time}`;
    }
    return null;
  }

  function sendToTom() {
    if (!inputTom.trim()) return;
    const userMsg = { from: "You → Tom", text: inputTom.trim() };
    setMessages((m) => [...m, userMsg]);
    setInputTom("");
    const local = getLocalTimeResponse(userMsg.text);
    if (local) {
      setMessages((m) => [...m, { from: "Tom", text: local }]);
      return;
    }
    // Local detection: immediately answer authorship questions without calling the AI
    const authorshipPattern = /who (made|created) this site|who made this site|who created this site|wer (hat )?(die|diese) seite (gemacht|erstellt)|wer hat diese seite gemacht|wer hat die seite gemacht/i;
    if (authorshipPattern.test(userMsg.text)) {
      const isGerman = /wer/i.test(userMsg.text);
      const credit = isGerman
        ? 'Diese Seite ist ein Demo fuer einen Quantum Portfolio Optimizer.'
        : 'This site is a demo for a quantum portfolio optimizer project.';
      setMessages((m) => [...m, { from: 'Tom', text: credit }]);
      return;
    }
    // Call the provided AI endpoint for Tom; payload uses { prompt: ... }
    const replyFromAI = async () => {
      setLoadingTom(true);
      try {
        const url = "https://cashxchain-ai-v1.cashxchain.workers.dev/";
        const fullPrompt = `${TOM_PERSONA_EXPLICIT}\n\nSiteContext: ${SITE_SUMMARY}\n\n${TOM_EXAMPLES}\nUser: ${userMsg.text}\n\nInstruction: Answer concisely. Do not reveal internal details about authorship unless explicitly asked.\nResponseFormat: Plain text only; do not wrap the answer in JSON or extra metadata.`;
        // Use a very low temperature for Tom to favour deterministic, technical replies
        const body = { prompt: fullPrompt, recipient: "Tom", context: SITE_SUMMARY, temperature: 0.02, max_tokens: 400 };
        // retry logic
        let resp = null; let txt = '';
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
            if (!resp.ok) throw new Error('AI_ERROR');
            txt = await resp.text();
            break;
          } catch (err) {
            if (attempt === 2) throw err;
            await new Promise((r) => setTimeout(r, 250 * (attempt + 1)));
          }
        }
        let data; try { data = JSON.parse(txt); } catch (e) { data = txt; }

        function extractReply(obj, raw) {
          if (typeof obj === 'string') return obj;
          if (!obj) return '';
          if (Array.isArray(obj.choices) && obj.choices.length) {
            const c = obj.choices[0];
            if (c.message && typeof c.message.content === 'string') return c.message.content;
            if (typeof c.text === 'string') return c.text;
          }
          const candidates = ['reply','response','text','output'];
          for (const k of candidates) if (typeof obj[k] === 'string' && obj[k].trim()) return obj[k];
          if (obj.result && typeof obj.result === 'object') {
            if (typeof obj.result.response === 'string') return obj.result.response;
            if (typeof obj.result.output === 'string') return obj.result.output;
          }
          if (obj.message && typeof obj.message === 'object' && typeof obj.message.content === 'string') return obj.message.content;
          if (typeof raw === 'string' && raw.trim()) return raw;
          try { return JSON.stringify(obj); } catch (e) { return ''; }
        }

        let reply = extractReply(data, txt);
        if (typeof reply === 'string') { reply = reply.trim().replace(/^Tom:\s*/i, ''); if (reply.length > 2000) reply = reply.slice(0,2000) + '...'; }
        // If AI echoed the site summary or credit when not asked, strip it
        if (!authorshipPattern.test(userMsg.text)) {
          if (typeof reply === 'string' && reply.includes('This demo site contains')) {
            reply = reply.replace(/This demo site contains[\s\S]*/i, '').trim();
          }
          if (!reply || reply.length < 6) reply = "Could you rephrase that? I'm not sure I understood.";
        }
        return reply;
      } finally {
        setLoadingTom(false);
      }
    };

    replyFromAI()
      .then((r) => {
        const replyText = (r && r.toString().trim().length > 0) ? r.toString() : "Thanks, I'll look into that.";
        setMessages((m) => {
          const lastTom = [...m].reverse().find((x) => x.from === 'Tom');
          if (lastTom && lastTom.text === replyText) {
            return [...m, { from: 'Tom', text: "I already mentioned that — do you want more details?" }];
          }
          return [...m, { from: 'Tom', text: replyText }];
        });
      })
      .catch(() => {
        setTimeout(() => {
          setMessages((m) => [...m, { from: "Tom", text: "Thanks, I'll look into that." }]);
        }, 600);
      });
  }

  // Johann has been moved to the FAQ page; this component now exposes Tom only.

  // Ensure Tom has a reminder of his name on mount
  useEffect(() => {
    setMessages((m) => {
      const hasTomReminder = m.some((x) => x.from === 'Tom' && /Tom/i.test(x.text));
      const additions = [];
      if (!hasTomReminder) additions.push({ from: 'Tom', text: 'Reminder: My name is Tom.' });
      return additions.length ? [...m, ...additions] : m;
    });
  }, []);

  // auto-scroll messages container to bottom when messages change
  useEffect(() => {
    try {
      const el = messagesContainerRef && messagesContainerRef.current;
      if (el) {
        const target = Math.max(0, el.scrollHeight - el.clientHeight + 30);
        el.scrollTop = Math.min(target, el.scrollHeight);
      }
    } catch (e) {
      // ignore
    }
  }, [messages]);

  // React to incoming blockchain event passed as prop `chainEvent`.
  useEffect(() => {
    try {
      if (!chainEvent) return;
      if (lastChainEventRef.current && lastChainEventRef.current.timestamp === chainEvent.timestamp) return;
      lastChainEventRef.current = chainEvent;

      const summary = `On-chain Event: ${chainEvent.type} — ${chainEvent.amount || ''} ${chainEvent.payer || ''} → ${chainEvent.payee || ''} (status: ${chainEvent.status})`;
      setMessages((m) => [...m, { from: 'System', text: summary }]);

      (async () => {
        try {
          const prompt = `AgentName: Tom\nPersona: ${TOM_PERSONA_EXPLICIT}\nDistinctness: Do NOT imitate or copy other site agents (e.g. Johann). Provide a brief, technical comment in 1-2 sentences. Return only the assistant text without leading 'Tom:'.\nResponseFormat: Plain text only; do not wrap the answer in JSON or extra metadata.\n\nSiteContext: ${SITE_SUMMARY}\n\nOn-chain event: ${summary}\n\nInstruction: Only reveal site authorship when explicitly asked.`;
          const url = "https://cashxchain-ai-v1.cashxchain.workers.dev/";
          const body = { prompt, recipient: 'Tom', context: SITE_SUMMARY };
          const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
          if (!resp.ok) throw new Error('AI_ERROR');
          const txt = await resp.text();
          let data;
          try { data = JSON.parse(txt); } catch(e) { data = txt; }
          function extractReply(obj, raw) {
            if (typeof obj === 'string') return obj;
            if (!obj) return '';
            if (Array.isArray(obj.choices) && obj.choices.length) {
              const c = obj.choices[0];
              if (c.message && typeof c.message.content === 'string') return c.message.content;
              if (typeof c.text === 'string') return c.text;
            }
            const candidates = ['reply','response','text','output'];
            for (const k of candidates) if (typeof obj[k] === 'string' && obj[k].trim()) return obj[k];
            if (obj.result && typeof obj.result === 'object') {
              if (typeof obj.result.response === 'string') return obj.result.response;
              if (typeof obj.result.output === 'string') return obj.result.output;
            }
            if (obj.message && typeof obj.message === 'object' && typeof obj.message.content === 'string') return obj.message.content;
            if (typeof raw === 'string' && raw.trim()) return raw;
            try { return JSON.stringify(obj); } catch (e) { return ''; }
          }
          let reply = extractReply(data, txt);
          if (typeof reply === 'string') {
            reply = reply.trim().replace(/^Tom:\s*/i, '');
            if (reply.length > 500) reply = reply.slice(0,500) + '...';
          }
          setMessages((m) => {
            const replyText = reply || 'Tom: Event recorded.';
            const lastTom = [...m].reverse().find((x) => x.from === 'Tom');
            if (lastTom && lastTom.text === replyText) {
              return [...m, { from: 'Tom', text: 'I already noted that event.' }];
            }
            return [...m, { from: 'Tom', text: replyText }];
          });
        } catch (e) {
          setMessages((m) => [...m, { from: 'Tom', text: 'Tom: I received the event and noted it.' }]);
        }
      })();
    } catch (e) {
      // ignore
    }
  }, [chainEvent]);

  if (bottomInputs) {
    return (
      <div style={{ position: "relative", width: "100%", minHeight: 260, color: "#e5e7eb" }}>
        <div style={{ padding: 12, minHeight: 260, boxSizing: "border-box", background: "#111827", borderRadius: 10, border: "1px solid #1f2937" }}>
          <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 8 }}>AI Agent — Tom</div>
          <div ref={messagesContainerRef} style={{ minHeight: 100, maxHeight: 140, overflow: 'auto', paddingRight: 8, paddingBottom: 60 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ margin: "6px 0" }}>
                <strong style={{ color: m.from === 'Tom' ? '#60a5fa' : '#d1d5db' }}>{m.from}:</strong>{' '}
                <span style={{ color: "#d1d5db" }}>{m.text}</span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input
              value={inputTom}
              onChange={(e) => setInputTom(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendToTom(); } }}
              placeholder="Message to Tom..."
              style={{ flex: 1, padding: 10, border: "1px solid #374151", borderRadius: 6, background: '#1f2937', color: '#e5e7eb' }}
            />
            <button onClick={sendToTom} disabled={loadingTom} style={{ padding: "10px 16px", borderRadius: 6, background: loadingTom ? "#374151" : "#2563eb", color: "#fff", border: "none", fontWeight: 600 }}>
              {loadingTom ? 'Sending...' : 'Send'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ padding: 16, background: "#111827", borderRadius: 10, border: "1px solid #1f2937", color: "#e5e7eb" }}>
      <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 10 }}>AI Agent — Tom</div>
      <div ref={messagesContainerRef} style={{ minHeight: 140, maxHeight: 220, padding: 10, background: "#0f172a", borderRadius: 6, overflow: 'auto' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "6px 0" }}>
            <strong style={{ color: m.from === 'Tom' ? '#60a5fa' : m.from === 'System' ? '#fbbf24' : '#d1d5db' }}>{m.from}:</strong>{' '}
            <span style={{ color: "#d1d5db" }}>{m.text}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <input
          value={inputTom}
          onChange={(e) => setInputTom(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendToTom(); } }}
          placeholder="Message to Tom..."
          style={{ flex: 1, padding: 10, border: "1px solid #374151", borderRadius: 6, fontSize: 14, background: "#1f2937", color: "#e5e7eb" }}
        />
        <button onClick={sendToTom} disabled={loadingTom} style={{ padding: "10px 16px", borderRadius: 6, background: loadingTom ? "#374151" : "#2563eb", color: "#fff", border: "none", fontWeight: 600 }}>
          {loadingTom ? 'Sending...' : 'Send'}
        </button>
      </div>
    </div>
  );
}
