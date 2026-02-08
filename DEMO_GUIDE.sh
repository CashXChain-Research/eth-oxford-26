#!/bin/bash

# Demo Quick-Start - CashXChain Quantum Vault
# ETH Oxford 2026

cat << 'EOF'

Demo Scenarios - CashXChain Quantum Vault
==========================================

Setup (Optional)
================

export SUI_NETWORK="devnet"
export SUI_RPC_URL="https://fullnode.devnet.sui.io"
export ORACLE_CONFIG_ID="0x..."
export PYTH_PRICE_FEED_ID="0x..."
export MAX_SLIPPAGE_BPS=100

Services
========

Terminal 1: FastAPI Server (port 3001)
  cd backend
  uvicorn blockchain.relayer_server:app --port 3001

Terminal 2: Event Provider WebSocket (port 3002)
  python3 -m blockchain.event_provider

Terminal 3: Async Relayer
  python3 -m blockchain.relayer

Demo A: Dry-Run (Safe - No Blockchain Submission)
===================================================

Shows optimization and PTB generation without chain action.

  curl -X POST http://localhost:3001/optimize \
    -H "Content-Type: application/json" \
    -d '{"portfolio_id":"0x123...","assets":["SUI","ETH","BTC"],"dry_run":true}'

Demo B: Live Trade (Blockchain Submission)
=============================================

Submits real transaction to Sui testnet.

  curl -X POST http://localhost:3001/optimize \
    -H "Content-Type: application/json" \
    -d '{"portfolio_id":"0x123...","assets":["SUI","ETH","BTC"],"dry_run":false}'

Demo C: CLI Agent Executor
===========================

  python3 -m blockchain.agent_executor demo 1000000
  python3 -m blockchain.agent_executor swap 1000000
  python3 -m blockchain.agent_executor quantum 1000000 900000 0.8
  python3 -m blockchain.agent_executor dryrun 1000000
  python3 -m blockchain.agent_executor killswitch

Results
=======

Dry-run:
  - Market Agent fetches prices
  - Execution Agent optimizes via QUBO
  - Risk Agent validates guardrails
  - Returns JSON with weights

Live trade:
  - Same as dry-run + Risk approval
  - Relayer submits PTB to Sui
  - Event Provider broadcasts updates

API: http://localhost:3001/docs
More: See backend/README.md, ARCHITECTURE.md, docs/agents.md

EOF
