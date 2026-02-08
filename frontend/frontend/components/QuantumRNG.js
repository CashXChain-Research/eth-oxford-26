"use client";
import React, { useState } from "react";

export default function QuantumRNG() {
  const [randomNumber, setRandomNumber] = useState(null);
  const [copied, setCopied] = useState(false);

  function generateRandomNumber() {
    const number = Math.floor(Math.random() * 1000);
    setRandomNumber(number);
  }

  async function copyToClipboard() {
    if (randomNumber === null) return;
    try {
      await navigator.clipboard.writeText(String(randomNumber));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error("Copy failed", err);
    }
  }

  return (
    <div style={{ margin: "30px", textAlign: "center" }}>
      <h2>Quantum RNG Demo</h2>
      <button
        onClick={generateRandomNumber}
        aria-label="Generate random number"
        className="inline-flex items-center justify-center gap-2 h-12 px-6 rounded-full bg-red-600 text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 transition"
      >
        <span className="font-medium">Generate</span>
        <span className="text-sm opacity-80">RNG</span>
      </button>

      {randomNumber !== null && (
        <div style={{ fontSize: "24px", marginTop: "20px", display: "flex", alignItems: "center", justifyContent: "center", gap: 12 }}>
          <span style={{ fontWeight: 600, marginRight: 8 }}>Your random number:</span>
          <span style={{ display: "inline-block", minWidth: 120, textAlign: "center", background: "rgba(220,38,38,0.12)", color: "#b91c1c", padding: "6px 12px", borderRadius: 6, fontFamily: "monospace", fontSize: 20 }}>
            {randomNumber}
          </span>
          <button
            onClick={copyToClipboard}
            aria-label="Copy random number to clipboard"
            style={{
              padding: "8px 12px",
              borderRadius: 6,
              border: "1px solid rgba(220,38,38,0.6)",
              background: copied ? "rgba(220,38,38,0.15)" : "transparent",
              color: "#b91c1c",
              cursor: "pointer",
              fontWeight: 600,
            }}
          >
            {copied ? "Copied!" : "Copy"}
          </button>
        </div>
      )}
    </div>
  );
}
