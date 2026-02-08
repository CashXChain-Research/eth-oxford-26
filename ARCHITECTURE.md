# Architecture

## Backend Structure (Three-Pillar Model)

```
backend/
├── agents/           Pillar 1: AI Agent Orchestration
├── quantum/          Pillar 2: Quantum Computing Backend
├── blockchain/       Pillar 3: Sui Verification Layer
├── core/             Shared Utilities
├── tests/            Validation & Benchmarking
└── api.py            FastAPI Main Entry
```

## Pillar 1: agents/
Multi-agent orchestration via LangGraph StateGraph.
- `manager.py` — Coordinates Market → Execution → Risk agents

## Pillar 2: quantum/
QUBO optimization and quantum random number generation.
- `optimizer.py` — QUBO solver (D-Wave, scipy backends)
- `rng.py` — Quantum RNG (AWS Braket)
- `optimize_and_send.py` — End-to-end pipeline

## Pillar 3: blockchain/
Sui blockchain integration and transaction settlement.
- `client.py` — Sui RPC client, state queries
- `ptb_builder.py` — Programmable Transaction Block builder
- `relayer.py` — Event listener, transaction relay
- `relayer_server.py` — FastAPI relayer (port 3001)
- `agent_executor.py` — CLI for trade execution
- `event_provider.py` — WebSocket event stream (port 3002)
- `gas_station.py` — Gas monitoring, auto-faucet

## Shared: core/
- `error_map.py` — Move error code mapping
- `market_data.py` — CoinGecko data fetcher

## Tests: tests/
- `backtester.py` — Historical performance simulation
- `benchmark_optimizer.py` — Classical optimizer comparison
- `attack_demo.py` — Safety validation
- `redline_tests.py` — Risk limit stress tests
- Unit tests: `test_qubo.py`, `test_error_map.py`, `test_scalability.py`

## Imports

```python
from agents.manager import run_pipeline
from quantum.optimizer import PortfolioQUBO
from blockchain.client import SuiTransactor
from core.error_map import parse_abort_error
from tests.backtester import compare_optimizers
```

## Key Principles

- Clear boundaries between pillars
- Pillars import only core/ for shared utilities
- Testable: comprehensive coverage across all layers
- Scalable: independent evolution of each pillar
