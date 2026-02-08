"use client";
import React, { useState } from "react";
import Link from 'next/link';
import QuantumRNG from "../components/QuantumRNG";
import AIAgents from "../components/AIAgents";
import MarketAgentConsole from "../components/MarketAgentConsole";
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
        <div style={{ textAlign: "center", marginBottom: 12, color: "#fff", textShadow: "0 1px 2px rgba(0,0,0,0.6)", display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h1 style={{ margin: 0 }}>Welcome to Our Demo Project!</h1>
            <p style={{ margin: 6 }}>Quantum RNG, AI Agents, and Sui Escrow – Demo</p>
          </div>
          <div style={{ marginLeft: 12 }}>
            <Link href="/faq" style={{ padding: '8px 12px', borderRadius: 8, background: '#fff', color: '#111', textDecoration: 'none', display: 'inline-block' }}>
              FAQ
            </Link>
          </div>
        </div>

        {/* semi-transparent overlay positioned to look like it's on the laptop screen */}
        <div style={{ width: "100%", display: "flex", justifyContent: "center" }}>
          <div style={{ width: 720, minHeight: 520, borderRadius: 10, overflow: "visible", boxShadow: "0 10px 30px rgba(0,0,0,0.6)", background: "rgba(255,255,255,0.0)" }}>
            {/* inner UI with slight translucent background so it reads on the background image */}
            <div style={{ padding: 12 }}>
              <QuantumRNG />
              <AIAgents bottomInputs={true} chainEvent={lastChainEvent} />
              <SuiEscrow onChainEvent={(ev) => setLastChainEvent(ev)} />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
