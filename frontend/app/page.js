"use client";
// page.js — CashXChain Quantum Vault · Single-Screen MVP
// AI-Powered Quantum Portfolio Optimization on Sui Blockchain

import React, { useState, useEffect, useRef, useCallback } from "react";
import dynamic from "next/dynamic";
import { API_BASE, WS_BASE } from "../utils/config";

const DAppKitClientProvider = dynamic(
  () => import("./DAppKitClientProvider").then((m) => m.DAppKitClientProvider),
  { ssr: false }
);
const WalletConnector = dynamic(
  () => import("../components/WalletConnector"),
  { ssr: false }
);
const BenchmarkComparison = dynamic(
  () => import("../components/BenchmarkComparison"),
  { ssr: false }
);
const AgentReasoning = dynamic(
  () => import("../components/AgentReasoning"),
  { ssr: false }
);
const SimulationResults = dynamic(
  () => import("../components/SimulationResults"),
  { ssr: false }
);

// ── Portfolio universe ────────────────────────────────────────
const PORTFOLIO = [
  { symbol: "SUI",  name: "Sui",       color: "#4da2ff", gradient: "linear-gradient(135deg, #4da2ff, #2563eb)" },
  { symbol: "BTC",  name: "Bitcoin",    color: "#f7931a", gradient: "linear-gradient(135deg, #f7931a, #ea580c)" },
  { symbol: "ETH",  name: "Ethereum",   color: "#627eea", gradient: "linear-gradient(135deg, #627eea, #818cf8)" },
  { symbol: "SOL",  name: "Solana",     color: "#9945ff", gradient: "linear-gradient(135deg, #9945ff, #c084fc)" },
  { symbol: "AVAX", name: "Avalanche",  color: "#e84142", gradient: "linear-gradient(135deg, #e84142, #f87171)" },
];

// ── Guardrails ────────────────────────────────────────────────
const GUARDRAILS = [
  { label: "Concentration Limit",  desc: "Max 40% allocation per asset",         icon: "shield" },
  { label: "Volume Cap",           desc: "Max 50 SUI daily trading volume",      icon: "chart" },
  { label: "On-Chain Enforcement", desc: "Blockchain rejects invalid trades",    icon: "lock" },
  { label: "QUBO Optimization",    desc: "Quantum-annealing portfolio solver",   icon: "atom" },
];

// ── SVG mini-icons ────────────────────────────────────────────
function Icon({ name, size = 18, color = "currentColor" }) {
  const icons = {
    shield: <path d="M12 2L3 7v5c0 5.25 3.82 10.13 9 11.27C17.18 22.13 21 17.25 21 12V7L12 2zm0 2.18l7 3.82v4c0 4.28-3.05 8.36-7 9.37C8.05 20.36 5 16.28 5 12V8l7-3.82z" fill={color}/>,
    chart: <path d="M3 13h2v8H3v-8zm6-6h2v14H9V7zm6-4h2v18h-2V3zm6 8h2v10h-2V11z" fill={color}/>,
    lock: <path d="M18 8h-1V6c0-2.76-2.24-5-5-5S7 3.24 7 6v2H6c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h12c1.1 0 2-.9 2-2V10c0-1.1-.9-2-2-2zM9 6c0-1.66 1.34-3 3-3s3 1.34 3 3v2H9V6zm9 14H6V10h12v10zm-6-3c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2z" fill={color}/>,
    atom: <><circle cx="12" cy="12" r="2.5" fill={color}/><ellipse cx="12" cy="12" rx="10" ry="4" fill="none" stroke={color} strokeWidth="1.2"/><ellipse cx="12" cy="12" rx="10" ry="4" fill="none" stroke={color} strokeWidth="1.2" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" fill="none" stroke={color} strokeWidth="1.2" transform="rotate(120 12 12)"/></>,
    brain: <path d="M12 2a7 7 0 0 0-4.6 12.3A4 4 0 0 0 8 18v2a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1v-2a4 4 0 0 0 .6-3.7A7 7 0 0 0 12 2zm2 16h-4v-1h4v1zm1.3-5.3l-.3.3v1H9v-1l-.3-.3A5 5 0 1 1 15.3 12.7z" fill={color}/>,
    zap: <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill={color}/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none">{icons[name]}</svg>;
}

// ── Helpers ───────────────────────────────────────────────────
function pct(v) {
  if (v == null || isNaN(v)) return "—";
  return (v * 100).toFixed(1) + "%";
}

// ── Glass card wrapper ────────────────────────────────────────
function GlassCard({ children, style, glow, ...props }) {
  return (
    <div
      style={{
        padding: 20,
        background: "rgba(17, 24, 39, 0.6)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderRadius: 16,
        border: "1px solid rgba(255,255,255,0.06)",
        boxShadow: glow || "0 4px 24px rgba(0,0,0,0.2)",
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
}

// ── Weight bar ────────────────────────────────────────────────
function WeightBar({ symbol, weight, selected, color, gradient }) {
  const w = Math.max(2, Math.round(weight * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
      <span style={{ width: 48, fontSize: 12, color: "#9ca3af", textAlign: "right", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 500 }}>
        {symbol}
      </span>
      <div style={{ flex: 1, height: 22, background: "rgba(31, 41, 55, 0.6)", borderRadius: 6, overflow: "hidden", position: "relative" }}>
        <div
          style={{
            width: `${w}%`,
            height: "100%",
            background: selected ? (gradient || color || "#3b82f6") : "rgba(75, 85, 99, 0.5)",
            borderRadius: 6,
            transition: "width 0.6s cubic-bezier(0.4, 0, 0.2, 1)",
            position: "relative",
          }}
        />
      </div>
      <span style={{ width: 52, fontSize: 13, color: selected ? "#fff" : "#9ca3af", fontFamily: "var(--font-geist-mono), monospace", fontWeight: 600 }}>
        {pct(weight)}
      </span>
    </div>
  );
}

// ── Pill tag ──────────────────────────────────────────────────
function Pill({ children, variant = "default" }) {
  const styles = {
    default: { background: "rgba(59,130,246,0.15)", color: "#93c5fd", border: "1px solid rgba(59,130,246,0.2)" },
    success: { background: "rgba(16,185,129,0.15)", color: "#6ee7b7", border: "1px solid rgba(16,185,129,0.2)" },
    danger: { background: "rgba(239,68,68,0.15)", color: "#fca5a5", border: "1px solid rgba(239,68,68,0.2)" },
    warning: { background: "rgba(245,158,11,0.15)", color: "#fcd34d", border: "1px solid rgba(245,158,11,0.2)" },
  };
  return (
    <span style={{ display: "inline-flex", alignItems: "center", padding: "3px 12px", borderRadius: 9999, fontSize: 12, fontWeight: 600, letterSpacing: "0.02em", ...styles[variant] }}>
      {children}
    </span>
  );
}

// ══════════════════════════════════════════════════════════════
//  MAIN PAGE COMPONENT
// ══════════════════════════════════════════════════════════════
function QuantumVault() {
  const [account, setAccount] = useState(null);
  const [loading, setLoading] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [logs, setLogs] = useState([]);
  const [health, setHealth] = useState(null);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);
  const logsEndRef = useRef(null);

  // Health check
  const checkHealth = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/health`);
      setHealth(await r.json());
    } catch { setHealth(null); }
  }, []);
  useEffect(() => { checkHealth(); const iv = setInterval(checkHealth, 15000); return () => clearInterval(iv); }, [checkHealth]);

  // WebSocket for live agent logs
  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(`${WS_BASE}/ws/logs`);
        wsRef.current = ws;
        ws.onopen = () => { setWsConnected(true); setLogs(l => [...l, { ts: Date.now(), msg: "Connected to AI agent pipeline" }]); };
        ws.onmessage = (e) => { try { const d = JSON.parse(e.data); if (d.type === "log") setLogs(l => [...l.slice(-200), { ts: Date.now(), msg: d.message }]); else if (d.type === "result") setResult(d.data); else if (d.type === "connected") setLogs(l => [...l, { ts: Date.now(), msg: d.message }]); } catch {} };
        ws.onclose = () => { setWsConnected(false); setTimeout(connect, 3000); };
        ws.onerror = () => ws.close();
      } catch { setTimeout(connect, 3000); }
    }
    connect();
    return () => { if (wsRef.current) wsRef.current.close(); };
  }, []);
  useEffect(() => { logsEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  // Pipeline call
  async function optimizeAndExecute() {
    setLoading(true); setError(null); setResult(null);
    setLogs(l => [...l, { ts: Date.now(), msg: "Launching quantum optimization pipeline..." }]);
    try {
      const r = await fetch(`${API_BASE}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ risk_tolerance: 0.5, user_id: account?.address || "anon", dry_run: false, use_mock: false }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setResult(j);
      setLogs(l => [...l, { ts: Date.now(), msg: `Pipeline finished — status: ${j.status}` }]);
    } catch (e) {
      setError(String(e));
      setLogs(l => [...l, { ts: Date.now(), msg: `Error: ${e}` }]);
    } finally { setLoading(false); }
  }

  // Dry-run simulation — runs pipeline but does NOT submit to chain
  async function simulateDryRun() {
    setSimulating(true); setError(null); setResult(null);
    setLogs(l => [...l, { ts: Date.now(), msg: "🔬 Launching dry-run simulation..." }]);
    try {
      const r = await fetch(`${API_BASE}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ risk_tolerance: 0.5, user_id: account?.address || "anon", dry_run: true, use_mock: false }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setResult(j);
      setLogs(l => [...l, { ts: Date.now(), msg: `🔬 Simulation complete — status: ${j.status}` }]);
    } catch (e) {
      setError(String(e));
      setLogs(l => [...l, { ts: Date.now(), msg: `Error: ${e}` }]);
    } finally { setSimulating(false); }
  }

  const isUp = health?.status === "ok";

  return (
    <div style={{ minHeight: "100vh", background: "#050509", color: "#e5e7eb", fontFamily: "var(--font-geist-sans), system-ui, sans-serif", position: "relative", overflow: "hidden" }}>

      {/* ── Ambient background glow ──────────────────────── */}
      <div style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none" }}>
        <div style={{ position: "absolute", top: "-20%", left: "-10%", width: "50%", height: "50%", background: "radial-gradient(circle, rgba(37,99,235,0.08) 0%, transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", bottom: "-10%", right: "-10%", width: "45%", height: "45%", background: "radial-gradient(circle, rgba(124,58,237,0.06) 0%, transparent 70%)", filter: "blur(80px)" }} />
        <div style={{ position: "absolute", top: "30%", right: "20%", width: "30%", height: "30%", background: "radial-gradient(circle, rgba(6,182,212,0.04) 0%, transparent 70%)", filter: "blur(60px)" }} />
      </div>

      {/* ── Header ──────────────────────────────────────── */}
      <header style={{
        display: "flex", justifyContent: "space-between", alignItems: "center",
        padding: "10px 28px",
        borderBottom: "1px solid rgba(255,255,255,0.05)",
        background: "rgba(5,5,9,0.7)",
        backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
        position: "sticky", top: 0, zIndex: 50,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: 8, background: "linear-gradient(135deg, #2563eb, #7c3aed)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Icon name="atom" size={16} color="#fff" />
            </div>
            <span style={{ fontSize: 17, fontWeight: 700, color: "#fff", letterSpacing: "-0.03em" }}>
              CashXChain
            </span>
          </div>
          <Pill>Quantum Vault</Pill>
          {/* Status dot */}
          <div style={{ display: "flex", alignItems: "center", gap: 5, marginLeft: 4 }}>
            <div style={{
              width: 7, height: 7, borderRadius: "50%",
              background: isUp ? "#10b981" : "#ef4444",
              boxShadow: isUp ? "0 0 8px rgba(16,185,129,0.6)" : "0 0 8px rgba(239,68,68,0.6)",
              animation: isUp ? undefined : "pulse 2s infinite",
            }} />
            <span style={{ fontSize: 11, color: isUp ? "#6ee7b7" : "#fca5a5", fontWeight: 500 }}>
              {isUp ? "Online" : "Offline"}
            </span>
          </div>
        </div>
        <WalletConnector onAccountChange={setAccount} />
      </header>

      {/* ── Main ────────────────────────────────────────── */}
      <main style={{ position: "relative", zIndex: 1, maxWidth: 880, margin: "0 auto", padding: "32px 24px 48px" }}>

        {/* ── Hero ──────────────────────────────────────── */}
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "4px 14px", borderRadius: 9999, background: "rgba(124,58,237,0.12)", border: "1px solid rgba(124,58,237,0.2)", marginBottom: 16 }}>
            <Icon name="atom" size={14} color="#c084fc" />
            <span style={{ fontSize: 12, fontWeight: 600, color: "#c084fc", letterSpacing: "0.04em", textTransform: "uppercase" }}>
              AI + Quantum + Blockchain
            </span>
          </div>
          <h1 style={{ fontSize: 36, fontWeight: 800, color: "#fff", lineHeight: 1.15, margin: "0 0 10px", letterSpacing: "-0.04em" }}>
            Quantum-Optimized
            <br />
            <span style={{ background: "linear-gradient(135deg, #60a5fa, #a78bfa, #c084fc)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              Portfolio Vault
            </span>
          </h1>
          <p style={{ fontSize: 15, color: "#6b7280", maxWidth: 520, margin: "0 auto", lineHeight: 1.6 }}>
            AI agents optimize your portfolio using quantum annealing (QUBO).
            Every trade is enforced by on-chain guardrails on the Sui blockchain.
            The AI decides — the blockchain enforces control.
          </p>
        </div>

        {/* ── Three pillars ─────────────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 28 }}>
          {[
            { icon: "brain", label: "AI Agents", desc: "Multi-agent pipeline with LangGraph", color: "#60a5fa" },
            { icon: "atom",  label: "Quantum Solver", desc: "QUBO optimization via annealing", color: "#a78bfa" },
            { icon: "lock",  label: "Sui Blockchain", desc: "Immutable on-chain trade guardrails", color: "#34d399" },
          ].map((p) => (
            <GlassCard key={p.label} style={{ textAlign: "center", padding: "20px 16px" }}>
              <div style={{
                width: 40, height: 40, borderRadius: 12, margin: "0 auto 10px",
                background: `${p.color}15`, border: `1px solid ${p.color}25`,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}>
                <Icon name={p.icon} size={20} color={p.color} />
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#fff", marginBottom: 4 }}>{p.label}</div>
              <div style={{ fontSize: 12, color: "#6b7280", lineHeight: 1.4 }}>{p.desc}</div>
            </GlassCard>
          ))}
        </div>

        {/* ── Portfolio & Guardrails ────────────────────── */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 24 }}>
          {/* Assets */}
          <GlassCard>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
              <Icon name="chart" size={16} color="#60a5fa" />
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>Portfolio Universe</span>
              <Pill>5 Assets</Pill>
            </div>
            {PORTFOLIO.map((a, i) => (
              <div key={a.symbol} style={{
                display: "flex", alignItems: "center", gap: 10, padding: "8px 0",
                borderBottom: i < PORTFOLIO.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              }}>
                <div style={{ width: 28, height: 28, borderRadius: 8, background: `${a.color}18`, border: `1px solid ${a.color}30`, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: a.color }}>{a.symbol.charAt(0)}</span>
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#e5e7eb" }}>{a.symbol}</div>
                  <div style={{ fontSize: 11, color: "#6b7280" }}>{a.name}</div>
                </div>
              </div>
            ))}
          </GlassCard>

          {/* Guardrails */}
          <GlassCard>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
              <Icon name="shield" size={16} color="#34d399" />
              <span style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>On-Chain Guardrails</span>
            </div>
            {GUARDRAILS.map((g, i) => (
              <div key={g.label} style={{
                display: "flex", alignItems: "flex-start", gap: 10, padding: "8px 0",
                borderBottom: i < GUARDRAILS.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              }}>
                <div style={{ width: 28, height: 28, borderRadius: 8, background: "rgba(52,211,153,0.08)", border: "1px solid rgba(52,211,153,0.15)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginTop: 1 }}>
                  <Icon name={g.icon} size={14} color="#34d399" />
                </div>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "#e5e7eb" }}>{g.label}</div>
                  <div style={{ fontSize: 11, color: "#6b7280", lineHeight: 1.4 }}>{g.desc}</div>
                </div>
              </div>
            ))}
          </GlassCard>
        </div>

        {/* ── CTA Buttons ──────────────────────────────── */}
        <div style={{ marginBottom: 24 }}>
          {!account ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, width: "100%" }}>
                <div
                  style={{
                    padding: "6px",
                    borderRadius: 16,
                    background: "linear-gradient(135deg, rgba(99,102,241,0.25), rgba(139,92,246,0.25))",
                    border: "1px solid rgba(139,92,246,0.3)",
                    display: "flex",
                    justifyContent: "center",
                    alignItems: "center",
                  }}
                >
                  <WalletConnector onAccountChange={setAccount} />
                </div>
                <button
                  onClick={simulateDryRun}
                  disabled={simulating || loading || !isUp}
                  className="cta-button"
                  style={{
                    width: "100%", padding: "16px 20px", borderRadius: 14,
                    border: "1px solid rgba(245,158,11,0.25)",
                    background: simulating ? "rgba(120,80,0,0.4)" : "rgba(245,158,11,0.08)",
                    color: "#fcd34d",
                    fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em",
                    cursor: simulating || loading || !isUp ? "not-allowed" : "pointer",
                    transition: "all 0.3s",
                    boxShadow: "0 4px 20px rgba(245,158,11,0.08)",
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                    {simulating ? (
                      <><span className="spinner" style={{ borderTopColor: "#fcd34d" }} /> Simulating...</>
                    ) : (
                      <>🔬 Simulate (Dry Run)</>
                    )}
                  </span>
                </button>
              </div>
              <p style={{ textAlign: "center", fontSize: 12, color: "#4b5563", margin: 0 }}>
                Connect your Sui wallet (Slush) to access the quantum optimizer
              </p>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              {/* Simulate (Dry Run) */}
              <button
                onClick={simulateDryRun}
                disabled={simulating || loading || !isUp}
                className="cta-button"
                style={{
                  width: "100%", padding: "16px 20px", borderRadius: 14,
                  border: "1px solid rgba(245,158,11,0.25)",
                  background: simulating ? "rgba(120,80,0,0.4)" : "rgba(245,158,11,0.08)",
                  color: "#fcd34d",
                  fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em",
                  cursor: simulating || loading || !isUp ? "not-allowed" : "pointer",
                  transition: "all 0.3s",
                  boxShadow: "0 4px 20px rgba(245,158,11,0.08)",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                  {simulating ? (
                    <><span className="spinner" style={{ borderTopColor: "#fcd34d" }} /> Simulating...</>
                  ) : (
                    <>🔬 Simulate (Dry Run)</>
                  )}
                </span>
              </button>
              {/* Execute */}
              <button
                onClick={optimizeAndExecute}
                disabled={loading || simulating || !isUp}
                className="cta-button"
                style={{
                  width: "100%", padding: "16px 20px", borderRadius: 14, border: "none",
                  background: loading ? "rgba(30,58,95,0.8)" : "linear-gradient(135deg, #2563eb 0%, #7c3aed 50%, #06b6d4 100%)",
                  color: "#fff",
                  fontWeight: 700, fontSize: 15, letterSpacing: "-0.01em",
                  cursor: loading || simulating || !isUp ? "not-allowed" : "pointer",
                  transition: "all 0.4s cubic-bezier(0.4, 0, 0.2, 1)",
                  boxShadow: !loading ? "0 8px 32px rgba(37,99,235,0.25), 0 2px 8px rgba(124,58,237,0.15)" : "none",
                }}
              >
                <span style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
                  {loading ? (
                    <><span className="spinner" /> Executing...</>
                  ) : (
                    <><Icon name="zap" size={18} color="#fff" /> Optimize &amp; Execute</>
                  )}
                </span>
              </button>
            </div>
          )}
        </div>

        {/* ── Error ─────────────────────────────────────── */}
        {error && (
          <GlassCard style={{ marginBottom: 20, borderColor: "rgba(239,68,68,0.2)" }} glow="0 4px 24px rgba(239,68,68,0.1)">
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 16 }}>&#x26A0;</span>
              <span style={{ fontSize: 13, color: "#fca5a5" }}>{error}</span>
            </div>
          </GlassCard>
        )}

        {/* ── Results ───────────────────────────────────── */}
        {result && (
          <GlassCard
            style={{ marginBottom: 24, borderColor: result.status === "rejected" ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.15)" }}
            glow={result.status === "rejected" ? "0 4px 32px rgba(239,68,68,0.08)" : "0 4px 32px rgba(16,185,129,0.08)"}
          >
            {/* Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <Icon name="zap" size={18} color="#60a5fa" />
                <span style={{ fontSize: 16, fontWeight: 700, color: "#fff" }}>Optimization Result</span>
              </div>
              <Pill variant={result.status === "approved" ? "success" : result.status === "rejected" ? "danger" : "warning"}>
                {result.status?.toUpperCase() || "UNKNOWN"}
              </Pill>
            </div>

            {/* Metrics grid */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
              {[
                { label: "Expected Return",  value: pct(result.expected_return), color: result.expected_return >= 0 ? "#10b981" : "#ef4444" },
                { label: "Portfolio Risk",    value: pct(result.expected_risk),   color: "#f59e0b" },
                { label: "Solver Engine",     value: result.solver || "—",        color: "#a78bfa" },
                { label: "Execution Time",    value: `${(result.total_time_s || 0).toFixed(2)}s`, color: "#60a5fa" },
              ].map((m) => (
                <div key={m.label} style={{ textAlign: "center", padding: "12px 8px", background: "rgba(255,255,255,0.02)", borderRadius: 10, border: "1px solid rgba(255,255,255,0.04)" }}>
                  <div style={{ fontSize: 10, color: "#6b7280", marginBottom: 4, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 500 }}>{m.label}</div>
                  <div style={{ fontSize: 20, fontWeight: 700, color: m.color, fontFamily: "var(--font-geist-mono), monospace" }}>
                    {m.value}
                  </div>
                </div>
              ))}
            </div>

            {/* Allocation bars */}
            {result.weights && Object.keys(result.weights).length > 0 && (
              <div style={{ marginBottom: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Allocation Weights
                </div>
                {Object.entries(result.weights)
                  .sort((a, b) => b[1] - a[1])
                  .map(([sym, w]) => {
                    const asset = PORTFOLIO.find(p => p.symbol === sym);
                    return <WeightBar key={sym} symbol={sym} weight={w} selected={result.allocation?.[sym] === 1} color={asset?.color} gradient={asset?.gradient} />;
                  })}
              </div>
            )}

            {/* Risk checks */}
            {result.risk_checks && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#6b7280", marginBottom: 8, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Guardrail Checks
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {Object.entries(result.risk_checks).map(([name, passed]) => (
                    <div key={name} style={{
                      display: "flex", alignItems: "center", gap: 6,
                      padding: "6px 14px", borderRadius: 8,
                      background: passed ? "rgba(16,185,129,0.1)" : "rgba(239,68,68,0.1)",
                      border: `1px solid ${passed ? "rgba(16,185,129,0.2)" : "rgba(239,68,68,0.2)"}`,
                    }}>
                      <span style={{ fontSize: 14 }}>{passed ? "\u2705" : "\u274C"}</span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: passed ? "#6ee7b7" : "#fca5a5", fontFamily: "var(--font-geist-mono), monospace" }}>
                        {name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Explorer */}
            {result.explorer_url && (
              <a href={result.explorer_url} target="_blank" rel="noopener noreferrer"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 16, fontSize: 13, color: "#60a5fa", textDecoration: "none", fontWeight: 500 }}>
                View on Sui Explorer
                <span style={{ fontSize: 14 }}>&rarr;</span>
              </a>
            )}

            {/* ── XAI: Agent Reasoning ──────────────────── */}
            {result.reasoning && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                <AgentReasoning reasoning={result.reasoning} />
              </div>
            )}

            {/* ── Dry-Run Simulation Results ─────────────── */}
            {result.simulation_results && (
              <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
                <SimulationResults
                  simulation={result.simulation_results}
                  slippage={result.slippage_estimates}
                  ptb={result.ptb_json}
                />
              </div>
            )}
          </GlassCard>
        )}

        {/* ── Agent Console ─────────────────────────────── */}
        <GlassCard style={{ padding: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon name="brain" size={16} color="#60a5fa" />
              <span style={{ fontSize: 13, fontWeight: 700, color: "#fff" }}>AI Agent Console</span>
              <div style={{
                width: 7, height: 7, borderRadius: "50%",
                background: wsConnected ? "#10b981" : "#f59e0b",
                boxShadow: wsConnected ? "0 0 8px rgba(16,185,129,0.5)" : "0 0 8px rgba(245,158,11,0.5)",
              }} />
              <span style={{ fontSize: 11, color: wsConnected ? "#6ee7b7" : "#fcd34d", fontWeight: 500 }}>
                {wsConnected ? "Live" : "Reconnecting"}
              </span>
            </div>
            <button
              onClick={() => setLogs([])}
              style={{
                padding: "4px 12px", borderRadius: 6,
                border: "1px solid rgba(255,255,255,0.06)",
                background: "rgba(255,255,255,0.03)",
                color: "#6b7280", fontSize: 11, cursor: "pointer", fontWeight: 500,
                transition: "all 0.2s",
              }}
            >
              Clear
            </button>
          </div>
          <div style={{
            maxHeight: 200, overflow: "auto", padding: 12,
            background: "rgba(0,0,0,0.3)", borderRadius: 10,
            fontFamily: "var(--font-geist-mono), monospace", fontSize: 12, color: "#94a3b8",
            border: "1px solid rgba(255,255,255,0.03)",
          }}>
            {logs.length === 0 ? (
              <div style={{ color: "#374151", fontStyle: "italic" }}>Awaiting pipeline execution...</div>
            ) : (
              logs.map((l, i) => (
                <div key={i} style={{ marginBottom: 3, lineHeight: 1.5 }}>
                  <span style={{ color: "#374151" }}>{new Date(l.ts).toLocaleTimeString()}</span>
                  {" "}
                  <span style={{ color: "#94a3b8" }}>{l.msg}</span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </GlassCard>

        {/* ── Quantum vs Classical Benchmark ────────────── */}
        <div style={{ marginTop: 24 }}>
          <BenchmarkComparison />
        </div>
      </main>

      {/* ── Footer ──────────────────────────────────────── */}
      <footer style={{
        position: "relative", zIndex: 1, textAlign: "center",
        padding: "20px 24px", borderTop: "1px solid rgba(255,255,255,0.04)",
        fontSize: 12, color: "#374151",
      }}>
        <span style={{ color: "#4b5563" }}>CashXChain Quantum Vault</span>
        <span style={{ margin: "0 8px", color: "#1f2937" }}>|</span>
        AI-Powered Portfolio Optimization on Sui
        <span style={{ margin: "0 8px", color: "#1f2937" }}>|</span>
        ETH Oxford 2026
      </footer>

      {/* ── Inline styles for animations ────────────────── */}
      <style jsx global>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
        .spinner {
          display: inline-block;
          width: 16px; height: 16px;
          border: 2px solid rgba(255,255,255,0.2);
          border-top-color: #fff;
          border-radius: 50%;
          animation: spin 0.7s linear infinite;
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
        .cta-button:not(:disabled):hover {
          transform: translateY(-1px);
          box-shadow: 0 12px 40px rgba(37,99,235,0.35), 0 4px 12px rgba(124,58,237,0.2) !important;
        }
        .cta-button:not(:disabled):active {
          transform: translateY(0);
        }
      `}</style>
    </div>
  );
}

// ── Export with dApp Kit provider ─────────────────────────────
export default function Page() {
  return (
    <DAppKitClientProvider>
      <QuantumVault />
    </DAppKitClientProvider>
  );
}
