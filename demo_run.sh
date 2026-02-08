#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════
#  CashXChain Quantum Vault — One-Click Demo Launcher
#  ETH Oxford 2026
# ═══════════════════════════════════════════════════════════
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend/frontend"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  CashXChain Quantum Vault — Demo Launcher${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════${NC}"
echo ""

# ── Cleanup on exit ──────────────────────────────────────
PIDS=()
cleanup() {
    echo -e "\n${YELLOW}Stopping all services...${NC}"
    for pid in "${PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    echo -e "${GREEN}All services stopped.${NC}"
}
trap cleanup EXIT INT TERM

# ── 1. Backend setup ─────────────────────────────────────
echo -e "${BLUE}[1/4]${NC} Setting up Python backend..."
cd "$BACKEND"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

# Ensure .env exists
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}  Created .env from .env.example — edit with real values for on-chain mode${NC}"
    fi
fi

pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# ── 2. Start Backend API (port 8000) ────────────────────
echo -e "${BLUE}[2/4]${NC} Starting Backend API on http://localhost:8000 ..."
cd "$BACKEND"
source .venv/bin/activate
uvicorn api:app --host 0.0.0.0 --port 8000 --reload &
PIDS+=($!)
sleep 2

# ── 3. Start Relayer Server (port 3001) ─────────────────
echo -e "${BLUE}[3/4]${NC} Starting Relayer on http://localhost:3001 ..."
cd "$BACKEND"
source .venv/bin/activate
uvicorn blockchain.relayer_server:app --host 0.0.0.0 --port 3001 --reload &
PIDS+=($!)
sleep 1

# ── 4. Start Frontend (port 3000) ───────────────────────
echo -e "${BLUE}[4/4]${NC} Starting Frontend on http://localhost:3000 ..."
cd "$FRONTEND"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm run dev &
PIDS+=($!)
sleep 2

# ── Ready! ───────────────────────────────────────────────
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  All services running!${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}Frontend:${NC}    http://localhost:3000"
echo -e "  ${BLUE}Backend API:${NC} http://localhost:8000"
echo -e "  ${BLUE}  /health${NC}    http://localhost:8000/health"
echo -e "  ${BLUE}  /optimize${NC}  POST http://localhost:8000/optimize"
echo -e "  ${BLUE}  /advisory${NC}  POST http://localhost:8000/advisory"
echo -e "  ${BLUE}  /portfolio${NC} http://localhost:8000/portfolio"
echo -e "  ${BLUE}  WebSocket${NC}  ws://localhost:8000/ws/logs"
echo -e "  ${BLUE}Relayer:${NC}     http://localhost:3001/api/health"
echo ""
echo -e "${YELLOW}Quick test:${NC}"
echo '  curl http://localhost:8000/health'
echo '  curl -X POST http://localhost:8000/optimize -H "Content-Type: application/json" -d '\''{"risk_tolerance": 0.5, "dry_run": true, "use_mock": true}'\'''
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all background processes
wait
