"use client";
import React, { useState } from "react";
import Link from "next/link";
import Dashboard from "../components/Dashboard";
import AIAgents from "../components/AIAgents";
import QuantumAuditLog from "../components/QuantumAuditLog";
import SuiEscrow from "../components/SuiEscrow";
import WalletConnector from "../components/WalletConnector";
import MarketAgentConsole from "../components/MarketAgentConsole";

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "agents", label: "AI Agents" },
  { id: "market", label: "Market Agent" },
  { id: "audit", label: "Audit Log" },
  { id: "escrow", label: "Escrow" },
];

export default function Page() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [lastChainEvent, setLastChainEvent] = useState(null);

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(145deg, #0a0a0f 0%, #0f172a 40%, #0c0c1a 100%)",
        color: "#e5e7eb",
        fontFamily: "var(--font-geist-sans), system-ui, sans-serif",
      }}
    >
      {/* ── Header ─────────────────────────────────────────── */}
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          padding: "12px 24px",
          borderBottom: "1px solid #1f2937",
          background: "rgba(0,0,0,0.4)",
          backdropFilter: "blur(12px)",
          position: "sticky",
          top: 0,
          zIndex: 50,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: "#fff", letterSpacing: "-0.02em" }}>
            CashXChain
          </div>
          <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 9999, background: "#1e3a5f", color: "#93c5fd" }}>
            Quantum Portfolio
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Link
            href="/faq"
            style={{
              padding: "6px 14px",
              borderRadius: 8,
              border: "1px solid #374151",
              color: "#9ca3af",
              textDecoration: "none",
              fontSize: 13,
            }}
          >
            FAQ
          </Link>
        </div>
      </header>

      {/* ── Tab Navigation ─────────────────────────────────── */}
      <nav
        style={{
          display: "flex",
          gap: 2,
          padding: "0 24px",
          background: "rgba(0,0,0,0.2)",
          borderBottom: "1px solid #1f2937",
          overflowX: "auto",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: "10px 18px",
              border: "none",
              borderBottom: activeTab === tab.id ? "2px solid #3b82f6" : "2px solid transparent",
              background: "transparent",
              color: activeTab === tab.id ? "#fff" : "#6b7280",
              fontWeight: activeTab === tab.id ? 600 : 400,
              fontSize: 14,
              cursor: "pointer",
              transition: "all 0.2s",
              whiteSpace: "nowrap",
            }}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* ── Main Content ───────────────────────────────────── */}
      <main style={{ maxWidth: 960, margin: "0 auto", padding: "20px 24px 40px" }}>
        {/* Wallet connector — always visible at top */}
        <div
          style={{
            marginBottom: 16,
            padding: 12,
            background: "#111827",
            borderRadius: 10,
            border: "1px solid #1f2937",
          }}
        >
          <WalletConnector onConnect={() => {}} />
        </div>

        {/* Tab content */}
        {activeTab === "dashboard" && <Dashboard />}
        {activeTab === "agents" && <AIAgents chainEvent={lastChainEvent} />}
        {activeTab === "market" && <MarketAgentConsole />}
        {activeTab === "audit" && <QuantumAuditLog />}
        {activeTab === "escrow" && (
          <SuiEscrow onChainEvent={(ev) => setLastChainEvent(ev)} />
        )}
      </main>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer
        style={{
          textAlign: "center",
          padding: "16px 24px",
          borderTop: "1px solid #1f2937",
          fontSize: 12,
          color: "#4b5563",
        }}
      >
        CashXChain Research — ETH Oxford Hackathon 2026
      </footer>
    </div>
  );
}
