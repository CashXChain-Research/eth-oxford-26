#!/usr/bin/env python3
"""
FastAPI Backend Server for CashXChain Quantum Portfolio Optimizer.

Endpoints:
    POST /optimize        — run full pipeline (Market → QUBO → Risk → TX)
    GET  /portfolio       — current portfolio state
    GET  /health          — health check
    WS   /ws/logs         — real-time agent logs via WebSocket

Start:
    uvicorn api:app --reload --port 8000

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents import run_pipeline, state_to_dict
from sui_client import SuiTransactor, get_portfolio_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("api")

# ── App ──────────────────────────────────────────────

app = FastAPI(
    title="CashXChain Quantum Portfolio Optimizer",
    description="AI Agents + QUBO optimization + Sui blockchain",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store for connected WebSocket clients
ws_clients: list[WebSocket] = []

# Last pipeline result (in-memory cache for demo)
last_result: Optional[dict] = None


# ── Models ───────────────────────────────────────────

class OptimizeRequest(BaseModel):
    risk_tolerance: float = Field(0.5, ge=0.0, le=1.0, description="0=conservative, 1=aggressive")
    user_id: str = Field("demo-user", description="User identifier")
    dry_run: bool = Field(True, description="If true, don't submit to chain")
    use_mock: bool = Field(False, description="Force mock market data for demo")


class OptimizeResponse(BaseModel):
    status: str
    approved: bool
    allocation: dict
    weights: dict
    expected_return: float
    expected_risk: float
    energy: float
    solver: str
    solver_time_s: float
    risk_checks: dict
    risk_report: str
    transaction: Optional[dict] = None
    logs: list[str]
    total_time_s: float


# ── Broadcast helper ─────────────────────────────────

async def broadcast_log(message: str):
    """Send a log message to all connected WebSocket clients."""
    dead = []
    for ws in ws_clients:
        try:
            await ws.send_json({"type": "log", "message": message, "timestamp": time.time()})
        except Exception:
            dead.append(ws)
    for ws in dead:
        ws_clients.remove(ws)


# ── Endpoints ────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "CashXChain Quantum Portfolio Optimizer",
        "timestamp": time.time(),
    }


@app.post("/optimize", response_model=OptimizeResponse)
async def optimize(req: OptimizeRequest):
    """
    Run the full optimization pipeline:
    MarketAgent → ExecutionAgent (QUBO) → RiskAgent → (optional) Sui TX
    """
    global last_result
    logger.info(f"Optimize request: risk={req.risk_tolerance}, user={req.user_id}")
    await broadcast_log(f"📨 Optimize request received (risk={req.risk_tolerance})")

    t0 = time.perf_counter()

    # Run agent pipeline
    await broadcast_log("🧠 Starting agent pipeline …")
    state = run_pipeline(user_id=req.user_id, risk_tolerance=req.risk_tolerance, use_mock=req.use_mock)

    # Broadcast agent logs in real-time
    for log_entry in state.logs:
        await broadcast_log(log_entry)

    opt = state.optimization_result
    tx_result = None

    if state.status == "approved" and opt:
        await broadcast_log("✅ Risk checks passed — preparing transaction …")
        transactor = SuiTransactor()

        if req.dry_run:
            tx = transactor._dry_run(opt.allocation, opt.weights, "QUBO optimization")
        else:
            tx = transactor.execute_rebalance(
                allocation=opt.allocation,
                weights=opt.weights,
                expected_return=opt.expected_return,
                expected_risk=opt.expected_risk,
                reason=f"QUBO | E(r)={opt.expected_return:.4f} σ={opt.expected_risk:.4f}",
            )

        tx_result = {
            "success": tx.success,
            "digest": tx.digest,
            "gas_used": tx.gas_used,
            "error": tx.error,
        }
        await broadcast_log(f"🔗 TX: {tx.digest} (success={tx.success})")
    elif state.status == "rejected":
        await broadcast_log(f"❌ Rejected: {state.risk_report}")

    elapsed = time.perf_counter() - t0
    await broadcast_log(f"⏱ Total time: {elapsed:.3f}s")

    response = OptimizeResponse(
        status=state.status,
        approved=state.risk_approved,
        allocation=opt.allocation if opt else {},
        weights=opt.weights if opt else {},
        expected_return=opt.expected_return if opt else 0,
        expected_risk=opt.expected_risk if opt else 0,
        energy=opt.energy if opt else 0,
        solver=opt.solver_used if opt else "none",
        solver_time_s=opt.solver_time_s if opt else 0,
        risk_checks=state.risk_checks,
        risk_report=state.risk_report,
        transaction=tx_result,
        logs=state.logs,
        total_time_s=elapsed,
    )

    last_result = response.dict()
    return response


@app.get("/portfolio")
async def portfolio():
    """Get current portfolio state from Sui + last optimization."""
    chain_state = get_portfolio_status()
    return {
        "on_chain": chain_state,
        "last_optimization": last_result,
        "timestamp": time.time(),
    }


@app.get("/last-result")
async def get_last_result():
    """Return the last optimization result (for polling)."""
    if last_result is None:
        return {"status": "no_result", "message": "No optimization has been run yet"}
    return last_result


# ── WebSocket for live logs ──────────────────────────

@app.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket):
    """
    WebSocket endpoint for real-time agent logs.
    Frontend connects here to show live "Agent Console".
    """
    await websocket.accept()
    ws_clients.append(websocket)
    logger.info(f"WebSocket client connected ({len(ws_clients)} total)")
    await websocket.send_json({
        "type": "connected",
        "message": "Connected to CashXChain Agent Console",
        "timestamp": time.time(),
    })
    try:
        while True:
            # Keep alive — also accept commands from frontend
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "optimize":
                # Allow triggering optimization via WebSocket too
                risk = msg.get("risk_tolerance", 0.5)
                await websocket.send_json({"type": "ack", "message": f"Starting optimization (risk={risk})"})
                state = run_pipeline(user_id="ws-user", risk_tolerance=risk)
                for log_entry in state.logs:
                    await websocket.send_json({"type": "log", "message": log_entry, "timestamp": time.time()})
                result = state_to_dict(state)
                await websocket.send_json({"type": "result", "data": result, "timestamp": time.time()})
            elif msg.get("action") == "ping":
                await websocket.send_json({"type": "pong", "timestamp": time.time()})
    except WebSocketDisconnect:
        ws_clients.remove(websocket)
        logger.info(f"WebSocket client disconnected ({len(ws_clients)} remaining)")


# ── Startup ──────────────────────────────────────────

@app.on_event("startup")
async def startup():
    logger.info("🚀 CashXChain API starting …")
    logger.info("   POST /optimize     — run quantum optimization")
    logger.info("   GET  /portfolio    — portfolio state")
    logger.info("   WS   /ws/logs      — live agent logs")
