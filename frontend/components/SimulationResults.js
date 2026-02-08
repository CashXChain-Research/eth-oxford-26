"use client";
import React from "react";

function formatUSD(v) {
  if (v == null || isNaN(v)) return "—";
  return "$" + Number(v).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPct(v) {
  if (v == null || isNaN(v)) return "—";
  return (v * 100).toFixed(4) + "%";
}

export default function SimulationResults({ simulation, slippage, ptb }) {
  if (!simulation) return null;

  const swaps = simulation.swaps || {};
  const totals = simulation.totals || {};
  const gas = simulation.estimated_gas || {};
  const swapEntries = Object.entries(swaps);

  return (
    <div
      style={{
        borderRadius: 14,
        border: "1px solid rgba(245,158,11,0.15)",
        background: "rgba(245,158,11,0.04)",
        padding: 20,
        marginBottom: 20,
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 18 }}>🔬</span>
          <span style={{ fontSize: 15, fontWeight: 700, color: "#fff" }}>
            Dry-Run Simulation
          </span>
          <span
            style={{
              fontSize: 10,
              padding: "3px 10px",
              borderRadius: 9999,
              background: "rgba(245,158,11,0.15)",
              color: "#fcd34d",
              border: "1px solid rgba(245,158,11,0.2)",
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
            }}
          >
            NOT EXECUTED
          </span>
        </div>
      </div>

      {/* Summary metrics */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 10,
          marginBottom: 18,
        }}
      >
        {[
          {
            label: "Total Value",
            value: formatUSD(totals.total_value_usd),
            color: "#60a5fa",
          },
          {
            label: "Total Slippage",
            value: formatUSD(totals.total_slippage_usd),
            color: "#f59e0b",
          },
          {
            label: "Avg Slippage",
            value: formatPct(totals.avg_slippage_pct / 100),
            color: "#a78bfa",
          },
          {
            label: "Est. Gas Cost",
            value: `${gas.estimated_sui_cost || "—"} SUI`,
            color: "#34d399",
          },
        ].map((m) => (
          <div
            key={m.label}
            style={{
              textAlign: "center",
              padding: "10px 6px",
              background: "rgba(0,0,0,0.2)",
              borderRadius: 10,
              border: "1px solid rgba(255,255,255,0.04)",
            }}
          >
            <div
              style={{
                fontSize: 9,
                color: "#6b7280",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
                fontWeight: 500,
                marginBottom: 4,
              }}
            >
              {m.label}
            </div>
            <div
              style={{
                fontSize: 17,
                fontWeight: 700,
                color: m.color,
                fontFamily: "var(--font-geist-mono), monospace",
              }}
            >
              {m.value}
            </div>
          </div>
        ))}
      </div>

      {/* Swap details table */}
      {swapEntries.length > 0 && (
        <div style={{ marginBottom: 14 }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: "#6b7280",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              marginBottom: 8,
            }}
          >
            Per-Swap Breakdown (Almgren-Chriss)
          </div>
          <div
            style={{
              background: "rgba(0,0,0,0.3)",
              borderRadius: 10,
              overflow: "hidden",
              border: "1px solid rgba(255,255,255,0.03)",
            }}
          >
            {/* Table header */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "60px 1fr 1fr 1fr 1fr",
                gap: 4,
                padding: "10px 14px",
                borderBottom: "1px solid rgba(255,255,255,0.05)",
                fontSize: 10,
                fontWeight: 600,
                color: "#4b5563",
                textTransform: "uppercase",
                letterSpacing: "0.06em",
              }}
            >
              <span>Asset</span>
              <span style={{ textAlign: "right" }}>Amount</span>
              <span style={{ textAlign: "right" }}>Impact</span>
              <span style={{ textAlign: "right" }}>Slippage</span>
              <span style={{ textAlign: "right" }}>Cost</span>
            </div>

            {/* Rows */}
            {swapEntries.map(([sym, swap], i) => (
              <div
                key={sym}
                style={{
                  display: "grid",
                  gridTemplateColumns: "60px 1fr 1fr 1fr 1fr",
                  gap: 4,
                  padding: "10px 14px",
                  borderBottom:
                    i < swapEntries.length - 1
                      ? "1px solid rgba(255,255,255,0.03)"
                      : "none",
                  fontSize: 12,
                  fontFamily: "var(--font-geist-mono), monospace",
                }}
              >
                <span style={{ fontWeight: 700, color: "#e5e7eb" }}>
                  {sym}
                </span>
                <span style={{ textAlign: "right", color: "#94a3b8" }}>
                  {formatUSD(swap.amount_usd)}
                </span>
                <span style={{ textAlign: "right", color: "#fcd34d" }}>
                  {formatPct(swap.market_impact_pct / 100)}
                </span>
                <span style={{ textAlign: "right", color: "#f59e0b" }}>
                  {formatPct(swap.slippage_pct / 100)}
                </span>
                <span style={{ textAlign: "right", color: "#fca5a5" }}>
                  {formatUSD(swap.slippage_usd)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Gas estimation */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 16,
          padding: "10px 14px",
          background: "rgba(0,0,0,0.2)",
          borderRadius: 8,
          border: "1px solid rgba(255,255,255,0.03)",
          fontSize: 12,
          color: "#6b7280",
        }}
      >
        <span>⛽ Gas: <strong style={{ color: "#94a3b8" }}>{gas.total_units || "—"}</strong> units</span>
        <span>|</span>
        <span>Computation: <strong style={{ color: "#94a3b8" }}>{gas.computation || "—"}</strong></span>
        <span>|</span>
        <span>Storage: <strong style={{ color: "#94a3b8" }}>{gas.storage || "—"}</strong></span>
        <span>|</span>
        <span>PTB size: <strong style={{ color: "#94a3b8" }}>{simulation.ptb_size_bytes || "—"} bytes</strong></span>
      </div>

      {/* Note */}
      <div
        style={{
          marginTop: 12,
          fontSize: 11,
          color: "#4b5563",
          fontStyle: "italic",
          textAlign: "center",
        }}
      >
        This is a simulation. No transaction was submitted to the blockchain.
        Click "Execute on Chain" to submit the actual transaction.
      </div>
    </div>
  );
}
