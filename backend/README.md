# Backend

Pure-Python backend for quantum portfolio optimizer.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Configure in .env:
# PACKAGE_ID, PORTFOLIO_ID, AGENT_CAP_ID, ADMIN_CAP_ID
```

## Services

FastAPI Relayer (port 3001):
```bash
uvicorn api:app --port 3001
# or
uvicorn blockchain.relayer_server:app --port 3001
```

Event Provider WebSocket (port 3002):
```bash
python3 -m blockchain.event_provider
```

Async Relayer:
```bash
python3 -m blockchain.relayer
```

Gas Monitor:
```bash
python3 -m blockchain.gas_station --watch
```

## CLI

```bash
python3 -m blockchain.agent_executor demo [amount_mist]
python3 -m blockchain.agent_executor swap [amount_mist]
python3 -m blockchain.agent_executor quantum [amount] [min] [score]
python3 -m blockchain.agent_executor dryrun [amount_mist]
python3 -m blockchain.agent_executor killswitch
python3 -m blockchain.agent_executor pause
python3 -m blockchain.agent_executor resume
python3 -m blockchain.agent_executor stream
```

## Code Quality

```bash
mypy .              # Type checking
black --check .     # Code formatting
isort --check-only .  # Import ordering
flake8 .            # Linting
pytest              # Tests
```

## Module Overview

agents/ (2 files)
  - manager.py: LangGraph StateGraph orchestrator

quantum/ (4 files)
  - optimizer.py: QUBO solver (D-Wave, scipy backends)
  - rng.py: Quantum RNG (AWS Braket)
  - optimize_and_send.py: End-to-end pipeline

blockchain/ (8 files)
  - client.py: Sui RPC client
  - ptb_builder.py: Programmable Transaction Block builder
  - relayer.py: Event listener and relay
  - relayer_server.py: FastAPI relayer service
  - agent_executor.py: CLI trade execution
  - event_provider.py: WebSocket event stream
  - gas_station.py: Gas monitoring

core/ (3 files)
  - error_map.py: Move error code mapping
  - market_data.py: CoinGecko data fetcher

tests/ (8 files)
  - integration_tests.py: Phase 2 feature validation + RNG integration
  - safety_tests.py: Kill-switch, redline, attack demos
  - backtester.py: Historical performance simulation
  - benchmark_optimizer.py: Classical optimizer comparison
  - test_qubo.py, test_error_map.py, test_scalability.py: Unit tests

## API

Main entry: api.py (FastAPI)

Endpoints:
  POST /optimize         Run full pipeline
  GET /portfolio         Current portfolio state
  GET /health           Health check
  WS /ws/logs           Real-time logs

## Environment Variables

See .env.example for all required variables.
