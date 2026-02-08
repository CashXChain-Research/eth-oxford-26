"use client";
import React, { useState } from "react";

// ── Agent icon + color mapping ────────────────────────────────
const AGENT_META = {
  MarketAgent: {
    label: "Market Intelligence",
    icon: "📊",
    color: "#60a5fa",
    borderColor: "rgba(96,165,250,0.2)",
    bgColor: "rgba(96,165,250,0.06)",
  },
  ExecutionAgent: {
    label: "Quantum Execution",
    icon: "⚛️",
    color: "#a78bfa",
    borderColor: "rgba(167,139,250,0.2)",
    bgColor: "rgba(167,139,250,0.06)",
  },
  RiskAgent: {
    label: "Risk Management",
    icon: "🛡️",
    color: "#34d399",
    borderColor: "rgba(52,211,153,0.2)",
    bgColor: "rgba(52,211,153,0.06)",
  },
};

const AGENT_ORDER = ["MarketAgent", "ExecutionAgent", "RiskAgent"];

export default function AgentReasoning({ reasoning }) {
  const [expandedAgent, setExpandedAgent] = useState(null);

  if (!reasoning || Object.keys(reasoning).length === 0) return null;

  return (
    <div style={{ marginBottom: 20 }}>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          marginBottom: 12,
        }}
      >
        <span style={{ fontSize: 16 }}>🧠</span>
        <span
          style={{
            fontSize: 14,
            fontWeight: 700,
            color: "#fff",
            letterSpacing: "-0.01em",
          }}
        >
          Explainable AI — Agent Reasoning
        </span>
        <span
          style={{
            fontSize: 10,
            padding: "2px 8px",
            borderRadius: 9999,
            background: "rgba(167,139,250,0.12)",
            color: "#c4b5fd",
            border: "1px solid rgba(167,139,250,0.2)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.04em",
          }}
        >
          XAI
        </span>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {AGENT_ORDER.filter((name) => reasoning[name]).map((name) => {
          const meta = AGENT_META[name] || {
            label: name,
            icon: "🤖",
            color: "#9ca3af",
            borderColor: "rgba(156,163,175,0.2)",
            bgColor: "rgba(156,163,175,0.06)",
          };
          const isExpanded = expandedAgent === name;
          const text = reasoning[name];

          return (
            <div
              key={name}
              style={{
                borderRadius: 12,
                border: `1px solid ${meta.borderColor}`,
                background: isExpanded ? meta.bgColor : "rgba(255,255,255,0.02)",
                overflow: "hidden",
                transition: "all 0.2s ease",
              }}
            >
              {/* Header — always visible, clickable */}
              <button
                onClick={() =>
                  setExpandedAgent(isExpanded ? null : name)
                }
                style={{
                  display: "flex",
                  alignItems: "center",
                  width: "100%",
                  gap: 10,
                  padding: "12px 16px",
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <span style={{ fontSize: 18 }}>{meta.icon}</span>
                <div style={{ flex: 1 }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: meta.color,
                    }}
                  >
                    {meta.label}
                  </div>
                  {!isExpanded && (
                    <div
                      style={{
                        fontSize: 11,
                        color: "#6b7280",
                        marginTop: 2,
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        maxWidth: 500,
                      }}
                    >
                      {text.split("\n")[0]}
                    </div>
                  )}
                </div>
                <span
                  style={{
                    fontSize: 12,
                    color: "#4b5563",
                    transform: isExpanded
                      ? "rotate(180deg)"
                      : "rotate(0deg)",
                    transition: "transform 0.2s",
                  }}
                >
                  ▼
                </span>
              </button>

              {/* Body — expanded content */}
              {isExpanded && (
                <div
                  style={{
                    padding: "0 16px 14px",
                    borderTop: `1px solid ${meta.borderColor}`,
                  }}
                >
                  <pre
                    style={{
                      margin: "12px 0 0",
                      fontSize: 12,
                      fontFamily:
                        "var(--font-geist-mono), monospace",
                      color: "#d1d5db",
                      lineHeight: 1.7,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {text}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
