<p align="center">
  <img src="https://img.shields.io/badge/ETH_Oxford-2026-blueviolet?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Sui-Blockchain-4DA2FF?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Quantum-Computing-FF6F00?style=for-the-badge" />
  <img src="https://img.shields.io/badge/AI-Agents-00C853?style=for-the-badge" />
</p>

<h1 align="center">⚛️ CashXChain Quantum Vault</h1>

<p align="center">
  <b>Quantum-optimized portfolio management on Sui — powered by AI agents</b>
</p>

<p align="center">
  <i>The first DeFi protocol that uses real quantum computing (D-Wave QUBO solvers) and multi-agent AI orchestration (LangGraph) to autonomously manage on-chain portfolios with provable risk guardrails.</i>
</p>

---

## 💡 The Problem

DeFi portfolio management today is either **fully manual** (users rebalancing by hand) or relies on **simplistic strategies** (equal-weight, fixed ratios). Classical optimization methods like Markowitz break down at scale with hundreds of correlated assets, and there's no way to verify that an AI agent is actually operating within safe boundaries on-chain.

## 🚀 Our Solution

**Quantum Vault** combines three cutting-edge technologies into one autonomous portfolio manager:

| Layer | Technology | What it does |
|:---:|:---:|---|
| 🧠 | **AI Agents** (LangGraph) | Multi-agent pipeline: Market Analysis → Quantum Optimization → Risk Validation |
| ⚛️ | **Quantum Computing** (D-Wave) | QUBO formulation solves portfolio allocation as a quantum optimization problem |
| ⛓️ | **Sui Blockchain** (Move) | On-chain guardrails, atomic rebalancing, and immutable audit trail |

**The key insight**: By encoding portfolio optimization as a QUBO problem, we can leverage quantum annealing to find near-optimal allocations across 200+ assets with **sub-linear scaling** — something impossible with classical solvers at the same speed.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (Next.js)                       │
│  Dashboard · AI Chat · Portfolio · Quantum RNG · Audit Log      │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                     FastAPI Backend (:3001)                      │
│                                                                  │
│  ┌──────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │  🧠 Agents   │  │  ⚛️ Quantum      │  │  ⛓️ Blockchain    │  │
│  │              │  │                  │  │                   │  │
│  │ Market Agent │→│ QUBO Optimizer   │→│ Sui RPC Client    │  │
│  │ Exec Agent   │  │ Quantum RNG      │  │ PTB Builder       │  │
│  │ Risk Agent   │  │ (D-Wave / AWS)   │  │ Relayer + Events  │  │
│  └──────────────┘  └──────────────────┘  └───────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ JSON-RPC + PTB
┌──────────────────────────▼──────────────────────────────────────┐
│                   Sui Blockchain (Move)                          │
│  Portfolio · Agent Registry · Oracle · Audit Trail               │
└─────────────────────────────────────────────────────────────────┘
```

### AI Agent Pipeline (LangGraph)

```
MarketAgent ──→ ExecutionAgent ──→ RiskAgent ──→ ✅ Approve / ❌ Reject
    │                │                  │
 Fetches         Runs QUBO          Validates
 prices &        optimization       guardrails
 sentiment       via D-Wave         & limits
```

1. **Market Agent** — Gathers real-time prices (CoinGecko, Pyth), calculates metrics & sentiment
2. **Execution Agent** — Formulates the QUBO matrix and solves via simulated annealing or QPU
3. **Risk Agent** — Validates spending caps, volume limits, concentration, slippage — approves or rejects

---

## ⚛️ Quantum Optimization — How It Works

We encode portfolio allocation as a **Quadratic Unconstrained Binary Optimization** (QUBO) problem:

$$E(x) = x^T Q x + c^T x$$

Where:
- $x \in \{0,1\}^n$ — binary allocation vector (invest in asset $i$ or not)
- $Q = \lambda_{\text{risk}} \cdot \Sigma$ — covariance matrix (penalizes correlated assets)
- $c = -\lambda_{\text{return}} \cdot \mu + \lambda_{\text{budget}} \cdot \text{penalty}$ — expected returns with budget constraint

**Solvers supported:**
| Solver | Use Case |
|--------|----------|
| D-Wave Simulated Annealing | Default — no cloud needed, fast |
| D-Wave QPU | Real quantum hardware via Leap |
| Exact Solver | Small problems (≤ 20 assets) |
| Scipy (Classical) | Benchmark comparison |

### 📊 Benchmark Results

Tested against 5 classical strategies over 60+ day backtests (BTC/ETH/SUI):

| Optimizer | Return | Risk | Sharpe |
|-----------|--------|------|--------|
| **QUBO (Ours)** | ✅ Competitive | ✅ Lower variance | ✅ Best risk-adjusted |
| Markowitz | High | High variance | Medium |
| HRP | Medium | Low | Good |
| Equal-Weight | Medium | Medium | Medium |
| Buy-and-Hold | Variable | Highest | Lowest |

**Scalability**: Validated up to **200 assets** with $O(n^{0.84})$ sub-linear complexity.

---

## 🛡️ On-Chain Guardrails (Move Smart Contracts)

Every trade is enforced by **immutable on-chain rules** — the AI agent *cannot* bypass them:

| Guardrail | Default | Purpose |
|-----------|---------|---------|
| ⏱️ Cooldown | 60s between trades | Prevents rapid-fire exploitation |
| 📊 Daily Volume Limit | 50 SUI | Caps total daily trade volume |
| 📉 Max Drawdown | 10% | Emergency stop if portfolio drops |
| 💱 Slippage Protection | 1% (100 bps) | Rejects trades with excessive slippage |
| 🚨 Kill Switch | Instant pause | Admin can freeze all trading |
| ❄️ Agent Freeze | Per-agent | Revoke individual agent access |

**Smart Contract Modules:**
- `portfolio.move` — Core vault logic, rebalancing, guardrails (1071 lines)
- `agent_registry.move` — Capability-based agent access control
- `oracle.move` — Pyth price feed integration
- `audit_trail.move` — Immutable quantum audit log with proof hashes

---

## 🔧 Tech Stack

| Component | Technology |
|-----------|-----------|
| **Quantum Solver** | D-Wave Ocean SDK, `dimod`, `dwave-neal` |
| **Quantum RNG** | AWS Braket (SV1 simulator / real QPU) |
| **AI Orchestration** | LangGraph, LangChain |
| **Backend** | Python, FastAPI, uvicorn |
| **Blockchain** | Sui (Move), `pysui` |
| **Frontend** | Next.js 16, React 19, Tailwind CSS 4 |
| **Wallet** | Mysten dApp Kit |
| **Price Feeds** | CoinGecko, Pyth Network |
| **Infra** | Railway (backend), Vercel (frontend) |

---

## ⚡ Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Sui CLI

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Configure: PACKAGE_ID, PORTFOLIO_ID, AGENT_CAP_ID, SUI_PRIVATE_KEY

# Start all services (3 terminals)
uvicorn blockchain.relayer_server:app --port 3001   # API Server
python3 -m blockchain.event_provider                 # WebSocket Events (:3002)
python3 -m blockchain.relayer                        # Async Relayer
```

### Frontend

```bash
cd frontend/frontend
npm install
npm run dev
# → http://localhost:3000
```

### Smart Contracts

```bash
cd backend/sui_contract
sui move build
sui client publish --gas-budget 200000000
```

---

## 🎬 Demo

### Dry Run (no blockchain submission)

```bash
curl -X POST http://localhost:3001/optimize \
  -H "Content-Type: application/json" \
  -d '{"portfolio_id":"0x...","assets":["SUI","ETH","BTC"],"dry_run":true}'
```

### Live Trade

```bash
curl -X POST http://localhost:3001/optimize \
  -H "Content-Type: application/json" \
  -d '{"portfolio_id":"0x...","assets":["SUI","ETH","BTC"],"dry_run":false}'
```

### CLI

```bash
python3 -m blockchain.agent_executor demo 1000000      # Full demo flow
python3 -m blockchain.agent_executor quantum 1000000    # Quantum-optimized trade
python3 -m blockchain.agent_executor killswitch         # Emergency stop
```

---

## 🧪 Testing

```bash
cd backend

# Unit tests
pytest tests/test_qubo.py           # QUBO solver correctness
pytest tests/test_error_map.py      # Move error code mapping

# Integration
pytest tests/integration_tests.py   # Full pipeline validation

# Benchmarks
python3 -m tests.benchmark_optimizer  # 5-optimizer comparison
python3 -m tests.backtester           # 60+ day historical backtest
python3 -m tests.test_scalability     # Scale to 200 assets

# Safety
pytest tests/safety_tests.py        # Kill-switch, redline, attack demos
```

---

## 📁 Project Structure

```
eth-oxford-26/
├── backend/
│   ├── agents/
│   │   └── manager.py              # LangGraph multi-agent orchestrator
│   ├── quantum/
│   │   ├── optimizer.py             # QUBO solver (461 lines)
│   │   ├── rng.py                   # Quantum RNG (AWS Braket)
│   │   └── optimize_and_send.py     # End-to-end pipeline
│   ├── blockchain/
│   │   ├── client.py                # Sui RPC client (384 lines)
│   │   ├── ptb_builder.py           # Programmable Transaction Blocks
│   │   ├── relayer.py               # Event listener & relay
│   │   ├── relayer_server.py        # FastAPI server (:3001)
│   │   ├── event_provider.py        # WebSocket stream (:3002)
│   │   ├── agent_executor.py        # CLI trade execution
│   │   └── gas_station.py           # Gas monitoring & auto-faucet
│   ├── core/
│   │   ├── error_map.py             # Move abort code → human messages
│   │   └── market_data.py           # CoinGecko price fetcher
│   ├── sui_contract/
│   │   └── sources/
│   │       ├── portfolio.move       # Core vault (1071 lines)
│   │       ├── agent_registry.move  # Agent access control
│   │       ├── oracle.move          # Pyth price feeds
│   │       └── audit_trail.move     # Immutable audit log
│   └── tests/                       # 8 test files
├── frontend/
│   └── frontend/                    # Next.js 16 app
│       ├── app/                     # Pages & API routes
│       └── components/              # Dashboard, Chat, Portfolio, etc.
├── docs/                            # Technical documentation
├── config.json                      # Deployment config
└── ARCHITECTURE.md                  # System design
```

---

## 👥 Team

| Name | Role | Focus |
|------|------|-------|
| **Korbinian** | CTO / Smart Contracts | Sui Move contracts, on-chain guardrails, deployment |
| **Valentin** | AI / Quantum Backend | QUBO optimizer, LangGraph agents, AWS Braket |

---

## 🏆 What Makes This Different

- **Not just another DeFi dashboard** — the AI agent *autonomously* manages your portfolio with quantum-optimized allocations
- **Provably safe** — guardrails are enforced **on-chain in Move**, not off-chain promises
- **Quantum advantage at scale** — sub-linear $O(n^{0.84})$ scaling means this works for institutional-sized portfolios (200+ assets)
- **Full audit trail** — every decision is logged on-chain with quantum proof hashes
- **Battle-tested** — 60+ day backtests, 5 optimizer benchmarks, attack simulations, kill-switch demos

---

<p align="center">
  <b>Built with ❤️ at ETH Oxford 2026</b>
</p>
