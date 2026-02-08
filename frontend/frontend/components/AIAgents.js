"use client";
import React, { useState, useRef, useEffect } from "react";

export default function AIAgents({ bottomInputs = false, chainEvent = null }) {
  const [messages, setMessages] = useState([
    { from: "Tom", text: "Hello! I'm Tom. How can I help?" },
  ]);
  // include the same site summary/credit so Tom has context about the demo
  const SITE_SUMMARY = `This demo site contains three main parts: (1) Quantum RNG UI demonstrating a random number generator component; (2) AI Agents demo where Tom responds to user messages and on-chain event comments; (3) a Sui Escrow demo that simulates (or uses a connected wallet for) simple escrow flows. The demo uses a public AI endpoint for agent replies. This site is created by the CashXChain Research department (Special Thanks to Dosentelefoni).`;
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
        ? 'Diese Seite wurde erstellt von CashXChain Research (Special Thanks to Dosentelefoni).'
        : 'This site was created by CashXChain Research (Special Thanks to Dosentelefoni).';
      setMessages((m) => [...m, { from: 'Tom', text: credit }]);
      return;
    }
    // Call the provided AI endpoint for Tom; payload uses { prompt: ... }
    const replyFromAI = async () => {
      setLoadingTom(true);
      try {
        const url = "https://cashxchain-ai-v1.cashxchain.workers.dev/";
        const fullPrompt = `${TOM_PERSONA_EXPLICIT}\n\nSiteContext: ${SITE_SUMMARY}\n\n${TOM_EXAMPLES}\nUser: ${userMsg.text}\n\nInstruction: Answer concisely. Only reveal site authorship (CashXChain Research, Dosentelefoni) when the user explicitly asks who created or maintains the site. Examples of explicit asks (English/German): 'who made this site', 'who created this site', 'wer hat diese Seite gemacht', 'wer hat die seite erstellt'. When those explicit phrases are used, respond with the credit string exactly: 'This site was created by CashXChain Research (Special Thanks to Dosentelefoni).' Otherwise do not reveal authorship.\nResponseFormat: Plain text only; do not wrap the answer in JSON or extra metadata.`;
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
          if (typeof reply === 'string' && (reply.includes('This demo site contains') || reply.includes('CashXChain Research') || reply.includes('Dosentelefoni'))) {
            reply = reply.replace(/This demo site contains[\s\S]*/i, '').replace(/CashXChain Research\s*\(?Special Thanks to Dosentelefoni\)?/i, '').trim();
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

  // If bottomInputs is true, we render the messages area and place inputs fixed
  // Ensure Tom and Johann have reminders of their own names so they "remember"
  useEffect(() => {
    setMessages((m) => {
      const hasTomReminder = m.some((x) => x.from === 'Tom' && /Tom/i.test(x.text));
      const additions = [];
      if (!hasTomReminder) additions.push({ from: 'Tom', text: 'Reminder: My name is Tom.' });
      return additions.length ? [...m, ...additions] : m;
    });
    // run only on mount
  }, []);

  if (bottomInputs) {
    return (
      <div style={{ position: "relative", width: 720, height: 260, margin: "0 auto", color: "#000" }}>
        <div style={{ padding: 12, height: "100%", boxSizing: "border-box", background: "rgba(255,255,255,0.95)", borderRadius: 8 }}>
          <h3 style={{ textAlign: "center", marginTop: 0 }}>AI Agents Demo</h3>
          <div ref={messagesContainerRef} style={{ minHeight: 140, maxHeight: 140, overflow: 'auto', paddingRight: 8, paddingBottom: 80 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ margin: "6px 0", color: "#000" }}>
                <strong>{m.from}:</strong> <span>{m.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ position: "absolute", left: 12, right: 12, bottom: 12, display: "flex", gap: 12, zIndex: 30, background: 'transparent' }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>To Tom (AI):</label>
            <div style={{ display: "flex", gap: 8, position: 'relative', zIndex: 40, background: '#fff', padding: 8, borderRadius: 8 }}>
              <input
                value={inputTom}
                onChange={(e) => setInputTom(e.target.value)}
                placeholder="Message to Tom (AI)"
                style={{ flex: 1, padding: 12, border: "2px solid #888", borderRadius: 8, boxShadow: "0 2px 6px rgba(0,0,0,0.12)", background: '#fff' }}
              />
              <button onClick={sendToTom} disabled={loadingTom} style={{ padding: "10px 14px", borderRadius: 8, background: loadingTom ? "#666" : "#111", color: "#fff", border: "none" }}>
                {loadingTom ? 'Sending...' : 'Send'}
              </button>
            </div>
            <div style={{ fontSize: 12, color: '#333', marginTop: 6 }}>Uses AI endpoint: https://cashxchain-ai-v1.cashxchain.workers.dev/</div>
          </div>
        </div>
      </div>
    );
  }

  // auto-scroll messages container to bottom when messages change
  useEffect(() => {
    try {
      const el = messagesContainerRef && messagesContainerRef.current;
      if (el) {
        // scroll so the bottom is visible plus extra 30px beyond the chat length
        const target = Math.max(0, el.scrollHeight - el.clientHeight + 30);
        // clamp target to scrollHeight
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
      // ignore if same event already handled
      if (lastChainEventRef.current && lastChainEventRef.current.timestamp === chainEvent.timestamp) return;
      lastChainEventRef.current = chainEvent;

      const summary = `On-chain Event: ${chainEvent.type} — ${chainEvent.amount || ''} ${chainEvent.payer || ''} → ${chainEvent.payee || ''} (status: ${chainEvent.status})`;
      setMessages((m) => [...m, { from: 'System', text: summary }]);

      // Ask Tom to comment briefly on the event
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

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", padding: 20, border: "1px solid #eee", borderRadius: 8, color: "#000" }}>
      <h2 style={{ textAlign: "center" }}>AI Agents Demo</h2>
      <div ref={messagesContainerRef} style={{ minHeight: 140, maxHeight: 220, padding: 10, background: "#fafafa", borderRadius: 6, color: "#000", overflow: 'auto' }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "6px 0", color: "#000" }}>
            <strong>{m.from}:</strong> <span>{m.text}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "block", marginTop: 12 }}>
        <div>
          <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>To Tom:</label>
          <input
            value={inputTom}
            onChange={(e) => setInputTom(e.target.value)}
            placeholder="Message to Tom"
            style={{ width: "100%", padding: 12, border: "1px solid #ccc", borderRadius: 6, fontSize: 15, background: "#fff", boxShadow: "inset 0 1px 2px rgba(0,0,0,0.03)" }}
          />
          <button onClick={sendToTom} style={{ marginTop: 8, padding: "10px 14px", borderRadius: 6, background: "#111", color: "#fff", border: "none" }}>
            Send to Tom
          </button>
        </div>
      </div>
    </div>
  );
}
