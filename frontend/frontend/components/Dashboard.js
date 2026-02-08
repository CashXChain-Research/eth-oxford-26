"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:3001";
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:3001";

// Replace this with your project name
const PROJECT_NAME = "YOUR_PROJECT_NAME";

// --- Helpers ----------------------------------------------------------------

function pct(v) {
  if (v == null || isNaN(v)) return "—";
  return (v * 100).toFixed(2) + "%";
}

function riskColor(val) {
  if (val <= 0.05) return "#10b981";
  if (val <= 0.15) return "#f59e0b";
  return "#ef4444";
}

function statusBadge(status) {
  const map = {
    approved: { bg: "#065f46", fg: "#6ee7b7", label: "Approved" },
    rejected: { bg: "#7f1d1d", fg: "#fca5a5", label: "Rejected" },
    pending_approval: { bg: "#78350f", fg: "#fcd34d", label: "Pending Approval" },
    advisory_approved: { bg: "#1e3a5f", fg: "#93c5fd", label: "Advisory OK" },
    advisory_rejected: { bg: "#4c1d1d", fg: "#fca5a5", label: "Advisory Warn" },
  };
  const s = map[status] || { bg: "#374151", fg: "#d1d5db", label: status || "Unknown" };
  return (
    <span
      style={{
        display: "inline-block",
        padding: "2px 10px",
        borderRadius: 9999,
        fontSize: 12,
        fontWeight: 600,
        background: s.bg,
        color: s.fg,
      }}
    >
      {s.label}
    </span>
  );
}

// --- Mini bar chart (pure CSS) -----------------------------------------------

function WeightBar({ symbol, weight, selected }) {
  const barWidth = Math.max(2, Math.round(weight * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
      <span style={{ width: 50, fontSize: 12, color: "#9ca3af", textAlign: "right", fontFamily: "monospace" }}>
        {symbol}
      </span>
      <div style={{ flex: 1, height: 16, background: "#1f2937", borderRadius: 4, overflow: "hidden" }}>
        <div
          style={{
            width: `${barWidth}%`,
            height: "100%",
            background: selected ? "#3b82f6" : "#4b5563",
            borderRadius: 4,
            transition: "width 0.4s ease",
          }}
        />
      </div>
      <span style={{ width: 50, fontSize: 12, color: "#d1d5db", fontFamily: "monospace" }}>
        {(weight * 100).toFixed(1)}%
      </span>
    </div>
  );
}

// --- Risk check list ---------------------------------------------------------

function RiskChecks({ checks }) {
  if (!checks || typeof checks !== "object") return null;
  const entries = Object.entries(checks);
  if (entries.length === 0) return null;
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: "#9ca3af", marginBottom: 6 }}>Risk Checks</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
        {entries.map(([name, passed]) => (
          <span
            key={name}
            style={{
              padding: "3px 10px",
              borderRadius: 6,
              fontSize: 12,
              background: passed ? "#064e3b" : "#7f1d1d",
              color: passed ? "#6ee7b7" : "#fca5a5",
              fontFamily: "monospace",
            }}
          >
            {passed ? "\u2713" : "\u2717"} {name}
          </span>
        ))}
      </div>
    </div>
  );
}

// =============================================================================
//  MAIN DASHBOARD COMPONENT
// =============================================================================

export default function Dashboard() {
  // --- Health ----------------------------------------------------------------
  const [health, setHealth] = useState(null);

  // --- Optimize controls -----------------------------------------------------
  const [riskTolerance, setRiskTolerance] = useState(0.5);
  const [dryRun, setDryRun] = useState(true);
  const [useMock, setUseMock] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  // --- Advisory --------------------------------------------------------------
  const [advisoryLoading, setAdvisoryLoading] = useState(false);
  const [advisory, setAdvisory] = useState(null);

  // --- Pending approvals -----------------------------------------------------
  const [pendingApprovals, setPendingApprovals] = useState([]);

  // --- Live logs via WebSocket -----------------------------------------------
  const [logs, setLogs] = useState([]);
  const [wsConnected, setWsConnected] = useState(false);
  const wsRef = useRef(null);
  const logsEndRef = useRef(null);

  // --- Health check ----------------------------------------------------------

  const checkHealth = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/health`);
      const j = await r.json();
      setHealth(j);
    } catch {
      setHealth(null);
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const iv = setInterval(checkHealth, 15000);
    return () => clearInterval(iv);
  }, [checkHealth]);

  // --- WebSocket connection --------------------------------------------------

  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(`${WS_BASE}/ws/logs`);
        wsRef.current = ws;
        ws.onopen = () => {
          setWsConnected(true);
          setLogs((l) => [...l, { ts: Date.now(), msg: "Connected to agent console" }]);
        };
        ws.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            if (data.type === "log") {
              setLogs((l) => [...l.slice(-200), { ts: Date.now(), msg: data.message }]);
            } else if (data.type === "result") {
              setResult(data.data);
            } else if (data.type === "connected") {
              setLogs((l) => [...l, { ts: Date.now(), msg: data.message }]);
            }
          } catch {
            // ignore
          }
        };
        ws.onclose = () => {
          setWsConnected(false);
          setTimeout(connect, 3000);
        };
        ws.onerror = () => {
          ws.close();
        };
      } catch {
        setTimeout(connect, 3000);
      }
    }
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
    };
  }, []);

  // auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  // --- Optimize action -------------------------------------------------------

  async function runOptimize() {
    setLoading(true);
    setError(null);
    setResult(null);
    setLogs((l) => [...l, { ts: Date.now(), msg: `Starting optimization (risk=${riskTolerance})...` }]);
    try {
      const r = await fetch(`${API_BASE}/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          risk_tolerance: riskTolerance,
          user_id: "frontend-user",
          dry_run: dryRun,
          use_mock: useMock,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setResult(j);
      setLogs((l) => [...l, { ts: Date.now(), msg: `Optimization complete: ${j.status}` }]);
      // Refresh pending approvals
      fetchPendingApprovals();
    } catch (e) {
      setError(String(e));
      setLogs((l) => [...l, { ts: Date.now(), msg: `Error: ${e}` }]);
    } finally {
      setLoading(false);
    }
  }

  // --- Advisory action -------------------------------------------------------

  async function runAdvisory() {
    setAdvisoryLoading(true);
    setAdvisory(null);
    try {
      const r = await fetch(`${API_BASE}/advisory`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          risk_tolerance: riskTolerance,
          user_id: "frontend-user",
          use_mock: useMock,
        }),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setAdvisory(j);
    } catch (e) {
      setAdvisory({ status: "error", recommendation: String(e) });
    } finally {
      setAdvisoryLoading(false);
    }
  }

  // --- Pending approvals -----------------------------------------------------

  const fetchPendingApprovals = useCallback(async () => {
    try {
      const r = await fetch(`${API_BASE}/pending-approvals`);
      const j = await r.json();
      setPendingApprovals(j.pending || []);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchPendingApprovals();
    const iv = setInterval(fetchPendingApprovals, 10000);
    return () => clearInterval(iv);
  }, [fetchPendingApprovals]);

  async function handleApproval(approvalId, action) {
    try {
      await fetch(`${API_BASE}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approval_id: approvalId, action }),
      });
      fetchPendingApprovals();
    } catch {
      // ignore
    }
  }

  // --- Render ----------------------------------------------------------------

  const isBackendUp = health && health.status === "ok";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── Health Status ─────────────────────────────────────── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: isBackendUp ? "#10b981" : "#ef4444",
              boxShadow: isBackendUp ? "0 0 8px #10b981" : "0 0 8px #ef4444",
            }}
          />
          <span style={{ fontSize: 13, color: isBackendUp ? "#6ee7b7" : "#fca5a5" }}>
            {isBackendUp ? "Backend Online" : "Backend Offline"}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "50%",
              background: wsConnected ? "#10b981" : "#f59e0b",
              boxShadow: wsConnected ? "0 0 8px #10b981" : "0 0 8px #f59e0b",
            }}
          />
          <span style={{ fontSize: 13, color: wsConnected ? "#6ee7b7" : "#fcd34d" }}>
            {wsConnected ? "WS Connected" : "WS Reconnecting..."}
          </span>
        </div>
      </div>

      {/* ── Controls ──────────────────────────────────────────── */}
      <div
        style={{
          padding: 16,
          background: "#111827",
          borderRadius: 10,
          border: "1px solid #1f2937",
        }}
      >
        <div style={{ fontSize: 14, fontWeight: 600, color: "#e5e7eb", marginBottom: 12 }}>
          Portfolio Optimization
        </div>

        {/* Risk tolerance slider */}
        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "flex", justifyContent: "space-between", fontSize: 13, color: "#9ca3af", marginBottom: 4 }}>
            <span>Risk Tolerance</span>
            <span style={{ fontFamily: "monospace", color: riskColor(riskTolerance) }}>
              {riskTolerance.toFixed(2)}
            </span>
          </label>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={riskTolerance}
            onChange={(e) => setRiskTolerance(parseFloat(e.target.value))}
            style={{ width: "100%", accentColor: "#3b82f6" }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "#6b7280" }}>
            <span>Conservative</span>
            <span>Aggressive</span>
          </div>
        </div>

        {/* Options */}
        <div style={{ display: "flex", gap: 16, marginBottom: 12 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#9ca3af", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              style={{ accentColor: "#3b82f6" }}
            />
            Dry Run
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13, color: "#9ca3af", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={useMock}
              onChange={(e) => setUseMock(e.target.checked)}
              style={{ accentColor: "#3b82f6" }}
            />
            Mock Data
          </label>
        </div>

        {/* Buttons */}
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={runOptimize}
            disabled={loading || !isBackendUp}
            style={{
              flex: 1,
              padding: "10px 16px",
              borderRadius: 8,
              border: "none",
              background: loading ? "#374151" : "#2563eb",
              color: "#fff",
              fontWeight: 600,
              fontSize: 14,
              cursor: loading || !isBackendUp ? "not-allowed" : "pointer",
              transition: "background 0.2s",
            }}
          >
            {loading ? "Running Pipeline..." : "Run Optimization"}
          </button>
          <button
            onClick={runAdvisory}
            disabled={advisoryLoading || !isBackendUp}
            style={{
              padding: "10px 16px",
              borderRadius: 8,
              border: "1px solid #374151",
              background: "transparent",
              color: "#93c5fd",
              fontWeight: 600,
              fontSize: 14,
              cursor: advisoryLoading || !isBackendUp ? "not-allowed" : "pointer",
            }}
          >
            {advisoryLoading ? "Analyzing..." : "Advisory Only"}
          </button>
        </div>

        {error && (
          <div style={{ marginTop: 8, padding: 8, background: "#7f1d1d", borderRadius: 6, fontSize: 13, color: "#fca5a5" }}>
            {error}
          </div>
        )}
      </div>

      {/* ── Results ───────────────────────────────────────────── */}
      {result && (
        <div
          style={{
            padding: 16,
            background: "#111827",
            borderRadius: 10,
            border: "1px solid #1f2937",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#e5e7eb" }}>
              Optimization Result
            </div>
            {statusBadge(result.status)}
          </div>

          {/* Key metrics */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
            {[
              { label: "Expected Return", value: pct(result.expected_return), color: result.expected_return >= 0 ? "#10b981" : "#ef4444" },
              { label: "Expected Risk", value: pct(result.expected_risk), color: riskColor(result.expected_risk) },
              { label: "Solver", value: result.solver, color: "#93c5fd" },
              { label: "Time", value: `${(result.total_time_s || 0).toFixed(2)}s`, color: "#d1d5db" },
            ].map((m) => (
              <div key={m.label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 11, color: "#6b7280", marginBottom: 2 }}>{m.label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: m.color, fontFamily: "monospace" }}>
                  {m.value}
                </div>
              </div>
            ))}
          </div>

          {/* Weights bar chart */}
          {result.weights && Object.keys(result.weights).length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: "#9ca3af", marginBottom: 6 }}>
                Allocation Weights
              </div>
              {Object.entries(result.weights)
                .sort((a, b) => b[1] - a[1])
                .map(([sym, w]) => (
                  <WeightBar
                    key={sym}
                    symbol={sym}
                    weight={w}
                    selected={result.allocation && result.allocation[sym] === 1}
                  />
                ))}
            </div>
          )}

          <RiskChecks checks={result.risk_checks} />

          {/* Risk report */}
          {result.risk_report && (
            <div style={{ marginTop: 12, padding: 10, background: "#0f172a", borderRadius: 6, fontSize: 12, color: "#94a3b8", fontFamily: "monospace", whiteSpace: "pre-wrap" }}>
              {result.risk_report}
            </div>
          )}

          {/* Explorer link */}
          {result.explorer_url && (
            <a
              href={result.explorer_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "inline-block", marginTop: 10, fontSize: 13, color: "#60a5fa", textDecoration: "underline" }}
            >
              View on Sui Explorer
            </a>
          )}

          {/* Dry-run PTB info */}
          {result.ptb_json && (
            <div style={{ marginTop: 8, padding: 8, background: "#0f172a", borderRadius: 6, fontSize: 11, color: "#6b7280", fontFamily: "monospace" }}>
              Dry-run PTB: {JSON.stringify(result.ptb_json, null, 2)}
            </div>
          )}
        </div>
      )}

      {/* ── Advisory Result ───────────────────────────────────── */}
      {advisory && (
        <div
          style={{
            padding: 16,
            background: "#111827",
            borderRadius: 10,
            border: "1px solid #1e3a5f",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "#93c5fd" }}>Advisory Result</div>
            {statusBadge(advisory.status)}
          </div>
          <div style={{ fontSize: 13, color: "#d1d5db", whiteSpace: "pre-wrap", fontFamily: "monospace" }}>
            {advisory.recommendation}
          </div>
        </div>
      )}

      {/* ── Pending Approvals ─────────────────────────────────── */}
      {pendingApprovals.length > 0 && (
        <div
          style={{
            padding: 16,
            background: "#111827",
            borderRadius: 10,
            border: "1px solid #78350f",
          }}
        >
          <div style={{ fontSize: 14, fontWeight: 600, color: "#fcd34d", marginBottom: 8 }}>
            Pending Approvals ({pendingApprovals.length})
          </div>
          {pendingApprovals.map((p) => (
            <div
              key={p.approval_id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: 10,
                background: "#1c1917",
                borderRadius: 6,
                marginBottom: 6,
              }}
            >
              <div>
                <div style={{ fontSize: 13, color: "#e5e7eb", fontFamily: "monospace" }}>
                  ID: {p.approval_id}
                </div>
                <div style={{ fontSize: 11, color: "#9ca3af" }}>
                  {p.reasons && p.reasons.join(", ")}
                </div>
              </div>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  onClick={() => handleApproval(p.approval_id, "approve")}
                  style={{ padding: "4px 12px", borderRadius: 6, border: "none", background: "#065f46", color: "#6ee7b7", fontSize: 12, cursor: "pointer" }}
                >
                  Approve
                </button>
                <button
                  onClick={() => handleApproval(p.approval_id, "reject")}
                  style={{ padding: "4px 12px", borderRadius: 6, border: "none", background: "#7f1d1d", color: "#fca5a5", fontSize: 12, cursor: "pointer" }}
                >
                  Reject
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Agent Console (Live Logs) ─────────────────────────── */}
      <div
        style={{
          padding: 16,
          background: "#111827",
          borderRadius: 10,
          border: "1px solid #1f2937",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: "#e5e7eb" }}>Agent Console</div>
          <button
            onClick={() => setLogs([])}
            style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #374151", background: "transparent", color: "#6b7280", fontSize: 12, cursor: "pointer" }}
          >
            Clear
          </button>
        </div>
        <div
          style={{
            maxHeight: 200,
            overflow: "auto",
            padding: 10,
            background: "#0f172a",
            borderRadius: 6,
            fontFamily: "monospace",
            fontSize: 12,
            color: "#94a3b8",
          }}
        >
          {logs.length === 0 ? (
            <div style={{ color: "#4b5563" }}>Waiting for agent activity...</div>
          ) : (
            logs.map((l, i) => (
              <div key={i} style={{ marginBottom: 2 }}>
                <span style={{ color: "#4b5563" }}>
                  {new Date(l.ts).toLocaleTimeString()}
                </span>{" "}
                {l.msg}
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </div>
  );
}
