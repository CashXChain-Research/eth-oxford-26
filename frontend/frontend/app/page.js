"use client";
import React, { useState } from "react";
import QuantumRNG from "../components/QuantumRNG";
import AIAgents from "../components/AIAgents";
import SuiEscrow from "../components/SuiEscrow";
import QuantumAuditLog from "../components/QuantumAuditLog";

export default function Page() {
  const [lastChainEvent, setLastChainEvent] = useState(null);
  return (
    <div
      style={{
        minHeight: "100vh",
        backgroundImage: "url('/hacker.png')",
        backgroundSize: "cover",
        backgroundPosition: "center",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 40,
      }}
    >
      <div style={{ width: 820, maxWidth: "95%", position: "relative" }}>
        <div style={{ textAlign: "center", marginBottom: 12, color: "#fff", textShadow: "0 1px 2px rgba(0,0,0,0.6)" }}>
          <h1 style={{ margin: 0 }}>Welcome to Our Demo Project!</h1>
          <p style={{ margin: 6 }}>Quantum RNG, AI Agents, and Sui Escrow – Demo</p>
        </div>

        {/* semi-transparent overlay positioned to look like it's on the laptop screen */}
        <div style={{ width: "100%", display: "flex", justifyContent: "center" }}>
          <div style={{ width: 720, minHeight: 520, borderRadius: 10, overflow: "visible", boxShadow: "0 10px 30px rgba(0,0,0,0.6)", background: "rgba(255,255,255,0.0)" }}>
            {/* inner UI with slight translucent background so it reads on the background image */}
            <div style={{ padding: 12 }}>
              <QuantumRNG />
              <AIAgents bottomInputs={true} chainEvent={lastChainEvent} />
              <QuantumAuditLog />
              <SuiEscrow onChainEvent={(ev) => setLastChainEvent(ev)} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
