# CashXChain Quantum Vault

ETH Oxford 2026 - Quantum Portfolio Optimization on Sui

**Status**: Production Ready

## Overview

Quantum-classical hybrid portfolio optimization for Sui blockchain.

Features:
- Quantum QUBO optimizer (D-Wave + scipy)
- Multi-agent orchestration (LangGraph)
- Price oracle integration (Pyth)
- Sui blockchain settlement
- Comprehensive benchmarking framework
- Scalability: 100-200+ assets (O(n^0.84))
- Real market validation: 60+ day backtests

## Quick Start

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Start services
uvicorn blockchain.relayer_server:app --port 3001  # Terminal 1
python3 -m blockchain.event_provider              # Terminal 2
python3 -m blockchain.relayer                     # Terminal 3

# Run tests
pytest tests/
```

## Architecture

Three-pillar backend structure:
- **agents/** - AI orchestration (LangGraph)
- **quantum/** - QUBO solver, quantum RNG
- **blockchain/** - Sui RPC, PTB builder, relayer
- **core/** - Shared utilities (error mapping, market data)
- **tests/** - Benchmarks, validation, attack simulations

See ARCHITECTURE.md for details.

## Documentation

- ARCHITECTURE.md - Code structure
- STATUS.md - Project milestones
- backend/README.md - Backend setup
- docs/agents.md - Agent design

## Project Layout

```
backend/
├── agents/manager.py             Multi-agent orchestrator
├── quantum/{optimizer,rng}.py    QUBO & quantum RNG
├── blockchain/{client,relayer...}.py  Sui integration
├── core/{error_map,market_data}.py    Shared utilities
├── tests/{backtester,benchmark...}.py Validation
├── api.py                        FastAPI entry
└── README.md                     Backend docs

frontend/          React/Next.js dashboard
sui_contract/      Move smart contracts
docs/              Technical documentation
```

## Key Results

Phase 2: Oracle sync, state reconciliation, real data backtesting, error mapping

Phase 3: Benchmark framework (5 optimizers), scalability (200 assets), sub-linear scaling

Code: Three-pillar architecture, 47 files reorganized, zero import errors
