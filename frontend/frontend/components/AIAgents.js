"use client";
import React, { useState, useRef, useEffect } from "react";

export default function AIAgents({ bottomInputs = false, chainEvent = null }) {
  const [messages, setMessages] = useState([
    { from: "Tom", text: "Hello! I'm Tom. How can I help?" },
    { from: "Johann", text: "Hi, I'm Johann. Ready for the demo." },
  ]);
  const [inputTom, setInputTom] = useState("");
  const [inputJohann, setInputJohann] = useState("");
  const [loadingTom, setLoadingTom] = useState(false);
  const [loadingJohann, setLoadingJohann] = useState(false);
  const messagesContainerRef = useRef(null);
  const lastChainEventRef = useRef(null);

  // Return a local time/date response if the user asked for time/date.
  function getLocalTimeResponse(text) {
    if (!text || typeof text !== 'string') return null;
    const t = text.toLowerCase();
    const timePattern = /zeit|uhr|wie spät|wie spät ist es|what time|current time|time now/;
    const datePattern = /datum|heute|welches datum|what date|date today|today/;
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
    // Call the provided AI endpoint for Tom; payload uses { prompt: ... }
    const replyFromAI = async () => {
      setLoadingTom(true);
      try {
        const url = "https://cashxchain-ai-v1.cashxchain.workers.dev/";
        const body = { prompt: userMsg.text, recipient: "Tom" };
        const resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!resp.ok) throw new Error("AI_ERROR");
        const txt = await resp.text();
        try {
          const data = JSON.parse(txt);
          return (
            (data && (data.reply || data.response || data.text)) ||
            (data && data.result && data.result.response) ||
            (typeof data === 'string' ? data : '')
          );
        } catch (e) {
          return txt;
        }
      } finally {
        setLoadingTom(false);
      }
    };

    replyFromAI()
      .then((r) => {
        if (r && r.toString().trim().length > 0) setMessages((m) => [...m, { from: "Tom", text: r.toString() }] );
        else setMessages((m) => [...m, { from: "Tom", text: "Tom: Thanks, I'll look into that." }]);
      })
      .catch(() => {
        setTimeout(() => {
          setMessages((m) => [...m, { from: "Tom", text: "Tom: Thanks, I'll look into that." }]);
        }, 600);
      });
  }

  function sendToJohann() {
    if (!inputJohann.trim()) return;
    const userMsg = { from: "You → Johann", text: inputJohann.trim() };
    setMessages((m) => [...m, userMsg]);
    setInputJohann("");
    const local = getLocalTimeResponse(userMsg.text);
    if (local) {
      setMessages((m) => [...m, { from: "Johann", text: local }]);
      return;
    }
      // Call the provided AI endpoint; payload uses { prompt: ... }
      const replyFromAI = async () => {
        const url = "https://cashxchain-ai-v1.cashxchain.workers.dev/";
        const body = { prompt: userMsg.text, recipient: "Johann" };
        const resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        if (!resp.ok) throw new Error("AI_ERROR");
        const txt = await resp.text();
        try {
          const data = JSON.parse(txt);
          return (
            (data && (data.reply || data.response || data.text)) ||
            (data && data.result && data.result.response) ||
            (typeof data === 'string' ? data : '')
          );
        } catch (e) {
          return txt;
        }
      };

      replyFromAI()
        .then((r) => {
          if (r && r.toString().trim().length > 0) setMessages((m) => [...m, { from: "Johann", text: r.toString() }] );
          else setMessages((m) => [...m, { from: "Johann", text: "Johann: Good idea, let's test it." }]);
        })
        .catch(() => {
          setTimeout(() => {
            setMessages((m) => [...m, { from: "Johann", text: "Johann: Good idea, let's test it." }]);
          }, 600);
        });
  }

  // If bottomInputs is true, we render the messages area and place inputs fixed
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
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>To Johann (AI):</label>
            <div style={{ display: "flex", gap: 8, position: 'relative', zIndex: 40, background: '#fff', padding: 8, borderRadius: 8 }}>
              <input
                value={inputJohann}
                onChange={(e) => setInputJohann(e.target.value)}
                placeholder="Message to Johann (AI)"
                style={{ flex: 1, padding: 12, border: "2px solid #888", borderRadius: 8, boxShadow: "0 2px 6px rgba(0,0,0,0.12)", background: '#fff' }}
              />
              <button onClick={sendToJohann} disabled={loadingJohann} style={{ padding: "10px 14px", borderRadius: 8, background: loadingJohann ? "#666" : "#111", color: "#fff", border: "none" }}>
                {loadingJohann ? 'Sending...' : 'Send'}
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
          const prompt = `You are Tom, provide a brief comment on the following on-chain event: ${summary} Please in 1-2 sentences.`;
          const url = "https://cashxchain-ai-v1.cashxchain.workers.dev/";
          const body = { prompt, recipient: 'Tom' };
          const resp = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
          if (!resp.ok) throw new Error('AI_ERROR');
          const txt = await resp.text();
          let data;
          try { data = JSON.parse(txt); } catch(e) { data = txt; }
          const reply = (data && (data.reply || data.response || data.text)) || (data && data.result && data.result.response) || (typeof data === 'string' ? data : '');
          setMessages((m) => [...m, { from: 'Tom', text: reply || 'Tom: Event recorded.' }]);
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
      <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
        <div style={{ flex: 1 }}>
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
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>To Johann:</label>
          <input
            value={inputJohann}
            onChange={(e) => setInputJohann(e.target.value)}
            placeholder="Message to Johann"
            style={{ width: "100%", padding: 12, border: "1px solid #ccc", borderRadius: 6, fontSize: 15, background: "#fff", boxShadow: "inset 0 1px 2px rgba(0,0,0,0.03)" }}
          />
          <button onClick={sendToJohann} style={{ marginTop: 8, padding: "10px 14px", borderRadius: 6, background: "#111", color: "#fff", border: "none" }}>
            Send to Johann
          </button>
        </div>
      </div>
    </div>
  );
}
