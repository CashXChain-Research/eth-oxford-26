"use client";
import React, { useState } from "react";

export default function AIAgents({ bottomInputs = false }) {
  const [messages, setMessages] = useState([
    { from: "Tom", text: "Hallo! Ich bin Tom. Wie kann ich helfen?" },
    { from: "Johann", text: "Hi, ich bin Johann. Bereit für die Demo." },
  ]);
  const [inputTom, setInputTom] = useState("");
  const [inputJohann, setInputJohann] = useState("");

  function sendToTom() {
    if (!inputTom.trim()) return;
    const userMsg = { from: "Du → Tom", text: inputTom.trim() };
    setMessages((m) => [...m, userMsg]);
    setInputTom("");
    setTimeout(() => {
      setMessages((m) => [...m, { from: "Tom", text: "Tom antwortet: Danke, ich schaue mir das an." }]);
    }, 600);
  }

  function sendToJohann() {
    if (!inputJohann.trim()) return;
    const userMsg = { from: "Du → Johann", text: inputJohann.trim() };
    setMessages((m) => [...m, userMsg]);
    setInputJohann("");
    setTimeout(() => {
      setMessages((m) => [...m, { from: "Johann", text: "Johann antwortet: Gute Idee, testen wir das." }]);
    }, 600);
  }

  // If bottomInputs is true, we render the messages area and place inputs fixed
  if (bottomInputs) {
    return (
      <div style={{ position: "relative", width: 720, height: 360, margin: "0 auto", color: "#000" }}>
        <div style={{ padding: 16, height: "100%", boxSizing: "border-box", overflow: "auto", background: "rgba(255,255,255,0.85)", borderRadius: 8 }}>
          <h3 style={{ textAlign: "center", marginTop: 0 }}>AI Agents Demo</h3>
          <div style={{ minHeight: 220 }}>
            {messages.map((m, i) => (
              <div key={i} style={{ margin: "6px 0", color: "#000" }}>
                <strong>{m.from}:</strong> <span>{m.text}</span>
              </div>
            ))}
          </div>
        </div>

        <div style={{ position: "absolute", left: 16, right: 16, bottom: 16, display: "flex", gap: 12 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>An Tom:</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={inputTom}
                onChange={(e) => setInputTom(e.target.value)}
                placeholder="Nachricht an Tom"
                style={{ flex: 1, padding: 10, border: "1px solid #ccc", borderRadius: 6 }}
              />
              <button onClick={sendToTom} style={{ padding: "10px 14px", borderRadius: 6, background: "#111", color: "#fff", border: "none" }}>
                Senden
              </button>
            </div>
          </div>
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>An Johann:</label>
            <div style={{ display: "flex", gap: 8 }}>
              <input
                value={inputJohann}
                onChange={(e) => setInputJohann(e.target.value)}
                placeholder="Nachricht an Johann"
                style={{ flex: 1, padding: 10, border: "1px solid #ccc", borderRadius: 6 }}
              />
              <button onClick={sendToJohann} style={{ padding: "10px 14px", borderRadius: 6, background: "#111", color: "#fff", border: "none" }}>
                Senden
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "40px auto", padding: 20, border: "1px solid #eee", borderRadius: 8, color: "#000" }}>
      <h2 style={{ textAlign: "center" }}>AI Agents Demo</h2>
      <div style={{ minHeight: 140, padding: 10, background: "#fafafa", borderRadius: 6, color: "#000" }}>
        {messages.map((m, i) => (
          <div key={i} style={{ margin: "6px 0", color: "#000" }}>
            <strong>{m.from}:</strong> <span>{m.text}</span>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>An Tom:</label>
          <input
            value={inputTom}
            onChange={(e) => setInputTom(e.target.value)}
            placeholder="Nachricht an Tom"
            style={{ width: "100%", padding: 12, border: "1px solid #ccc", borderRadius: 6, fontSize: 15, background: "#fff", boxShadow: "inset 0 1px 2px rgba(0,0,0,0.03)" }}
          />
          <button onClick={sendToTom} style={{ marginTop: 8, padding: "10px 14px", borderRadius: 6, background: "#111", color: "#fff", border: "none" }}>
            Senden an Tom
          </button>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", marginBottom: 6, fontWeight: 600 }}>An Johann:</label>
          <input
            value={inputJohann}
            onChange={(e) => setInputJohann(e.target.value)}
            placeholder="Nachricht an Johann"
            style={{ width: "100%", padding: 12, border: "1px solid #ccc", borderRadius: 6, fontSize: 15, background: "#fff", boxShadow: "inset 0 1px 2px rgba(0,0,0,0.03)" }}
          />
          <button onClick={sendToJohann} style={{ marginTop: 8, padding: "10px 14px", borderRadius: 6, background: "#111", color: "#fff", border: "none" }}>
            Senden an Johann
          </button>
        </div>
      </div>
    </div>
  );
}
