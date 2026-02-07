# Agent Architecture — CashXChain Quantum Portfolio Optimizer

## Overview

Three AI agents orchestrated via **LangGraph** optimize a crypto portfolio
using **quantum computing (QUBO)** and enforce risk constraints before
executing on the **Sui blockchain**.

```
┌─────────────────────────────────────────────────────────────────┐
│                        LangGraph Pipeline                       │
│                                                                 │
│  ┌──────────────┐   ┌──────────────────┐   ┌────────────────┐  │
│  │ Market Agent  │──▶│ Execution Agent   │──▶│  Risk Agent    │  │
│  │              │   │ (Quantum Solver)  │   │ (Pre-flight)   │  │
│  └──────────────┘   └──────────────────┘   └───────┬────────┘  │
│                                                     │           │
│                                            ┌────────▼────────┐  │
│                                            │  Approved?       │  │
│                                            │  ✅ → Sui TX    │  │
│                                            │  ❌ → Reject    │  │
│                                            └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     Sui Blockchain (Devnet)    │
              │  ┌─────────────────────────┐  │
              │  │ PortfolioState (shared)  │  │
              │  │ ExecutionGuardrails      │  │
              │  │ AuditLog (events)        │  │
              │  └─────────────────────────┘  │
              └───────────────────────────────┘
```

## Agent Details

### 1. Market Intelligence Agent
- **Input:** User risk tolerance (0-1)
- **Output:** 5 assets with expected returns + covariance matrix
- **Current:** Mock data (SUI, ETH, BTC, SOL, AVAX)
- **Production:** CoinGecko API, Pyth Network oracles, on-chain TVL data

### 2. Execution Agent (Quantum Solver)
- **Input:** Assets + covariance from Market Agent
- **Output:** Binary allocation vector + portfolio metrics
- **Method:** QUBO (Quadratic Unconstrained Binary Optimization)
- **Formula:** $E(x) = x^T Q x + c^T x$
  - $Q = \lambda_{risk} \cdot \Sigma$ (covariance → risk penalty)
  - $c = -\lambda_{return} \cdot \mu + \lambda_{budget} \cdot \text{penalty}$
- **Solver:** D-Wave SimulatedAnnealing (hackathon) / QPU (production)
- **Constraint:** Must solve in < 5 seconds

### 3. Risk Management Agent (Pre-Flight)
- **Input:** Optimization result from Execution Agent
- **Output:** Approve / Reject with detailed check report
- **Checks:**
  | Check | Threshold | Description |
  |-------|-----------|-------------|
  | `position_size_ok` | ≤ 40% | No single asset > 40% weight |
  | `risk_within_limit` | σ ≤ 0.35 | Portfolio annualized risk cap |
  | `return_sufficient` | ≥ 5% | Minimum expected return |
  | `solver_fast_enough` | ≤ 5s | Solver latency budget |
  | `optimizer_feasible` | — | QUBO feasibility flag |
  | `assets_selected` | ≥ 1 | At least one asset chosen |

## Data Flow

```
User clicks "Optimize" on Frontend
        │
        ▼
┌─ MarketAgent ─────────────────────────────┐
│  Fetch prices, compute μ (returns),       │
│  Σ (covariance), adjust for sentiment     │
└───────────────────────┬───────────────────┘
                        │
                        ▼
┌─ ExecutionAgent ──────────────────────────┐
│  Build QUBO: E(x) = xᵀQx + cᵀx          │
│  Solve via SimulatedAnnealing / D-Wave    │
│  Return: allocation, weights, E(r), σ     │
└───────────────────────┬───────────────────┘
                        │
                        ▼
┌─ RiskAgent ───────────────────────────────┐
│  Check 6 guardrails                       │
│  Match on-chain ExecutionGuardrails       │
│  Output: APPROVED or REJECTED + reason    │
└───────────────────────┬───────────────────┘
                        │
                ┌───────┴───────┐
                │   Approved?   │
                └───┬───────┬───┘
                YES │       │ NO
                    ▼       ▼
            Sign & Submit   Return error
            to Sui          to Frontend
                │
                ▼
        On-chain: PortfolioState updated
        On-chain: AuditLog event emitted
        Frontend: shows tx digest + new state
```

## File Map

| File | Purpose |
|------|---------|
| `qubo_optimizer.py` | QUBO formulation, solver, test universe |
| `agents.py` | LangGraph pipeline (Market → Execution → Risk) |
| `sui_client.py` | Sui JSON-RPC client + transaction builder |
| `optimize_and_send.py` | End-to-end demo script |
| `test_qubo.py` | Unit tests + benchmarks |
| `relayer.py` | Event listener (legacy, for agent registration) |
| `quantum_rng.py` | AWS Braket quantum RNG (separate feature) |

## Quick Start

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # fill in contract addresses

# Run the optimizer standalone
python qubo_optimizer.py --target 3

# Run the full agent pipeline
python agents.py --risk 0.5

# Run end-to-end with Sui (dry-run)
python optimize_and_send.py --dry-run

# Run tests
python test_qubo.py -v
```
