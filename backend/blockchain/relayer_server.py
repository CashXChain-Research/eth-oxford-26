#!/usr/bin/env python3
"""
relayer_server.py — FastAPI Relayer Service

Accepts optimized portfolio weights from the Python AI pipeline via REST,
builds PTBs via sui CLI, and submits to Sui testnet.

Endpoints:
    POST /api/trade              — Execute a quantum-optimized trade
    POST /api/atomic-rebalance   — Multi-swap atomic rebalance
    POST /api/oracle-swap        — Oracle-validated swap
    POST /api/audit              — Log a quantum proof hash on-chain
    POST /api/pause              — Emergency kill-switch (admin only)
    GET  /api/status             — Portfolio status + gas balance
    GET  /api/health             — Health check

Start:
    uvicorn relayer_server:app --host 0.0.0.0 --port 3001 --reload
"""

import hashlib
import json
import logging
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.error_map import error_response_body, log_error, parse_abort_error
from blockchain.ptb_builder import (
    TxResult,
    _run_sui_cmd,
    build_atomic_rebalance,
    build_execute_rebalance,
    build_log_execution,
    build_oracle_validated_swap,
    build_set_paused,
    build_swap_and_rebalance,
)

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

PORT = int(os.getenv("RELAYER_PORT", "3001"))
NETWORK = os.getenv("SUI_NETWORK", "devnet")
RPC_URL = os.getenv("SUI_RPC_URL", f"https://fullnode.{NETWORK}.sui.io:443")

PACKAGE_ID = os.getenv("PACKAGE_ID", "")
PORTFOLIO_ID = os.getenv("PORTFOLIO_ID", os.getenv("PORTFOLIO_OBJECT_ID", ""))
AGENT_CAP_ID = os.getenv("AGENT_CAP_ID", "")
ADMIN_CAP_ID = os.getenv("ADMIN_CAP_ID", "")
ORACLE_CONFIG_ID = os.getenv("ORACLE_CONFIG_ID", "")

# ═══════════════════════════════════════════════════════════
#  PROTOCOL WHITELIST (backend-side enforcement)
# ═══════════════════════════════════════════════════════════

# Load whitelist from env (comma-separated addresses) or default to empty (allow all)
_whitelist_env = os.getenv("PROTOCOL_WHITELIST", "")
PROTOCOL_WHITELIST: set[str] = (
    {addr.strip() for addr in _whitelist_env.split(",") if addr.strip()}
    if _whitelist_env
    else set()
)


def check_protocol_whitelist(protocol_address: Optional[str] = None):
    """
    Validate that a target protocol address is whitelisted.
    If the whitelist is empty, all protocols are allowed (demo mode).
    """
    if not PROTOCOL_WHITELIST:
        return  # empty whitelist = permissive mode
    if protocol_address and protocol_address not in PROTOCOL_WHITELIST:
        raise HTTPException(
            status_code=403,
            detail=f"Protocol {protocol_address} is not whitelisted. "
            f"Allowed: {list(PROTOCOL_WHITELIST)}",
        )

# ═══════════════════════════════════════════════════════════
#  RPC HELPER
# ═══════════════════════════════════════════════════════════

_rpc_id = 0


def _rpc_call(method: str, params: list) -> dict:
    global _rpc_id
    _rpc_id += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _rpc_id,
        "method": method,
        "params": params,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result", {})


# ═══════════════════════════════════════════════════════════
#  FASTAPI APP
# ═══════════════════════════════════════════════════════════

app = FastAPI(
    title="quantum_vault Relayer",
    description="Relay service for quantum-optimized portfolio trades on Sui",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Health check ─────────────────────────────────────────


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "network": NETWORK,
        "rpc": RPC_URL,
        "package": PACKAGE_ID,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ── Portfolio status ─────────────────────────────────────


@app.get("/api/status")
async def status():
    try:
        obj = _rpc_call(
            "sui_getObject",
            [
                PORTFOLIO_ID,
                {"showContent": True, "showType": True, "showOwner": True},
            ],
        )
        fields = obj.get("data", {}).get("content", {}).get("fields", {})

        return {
            "portfolio": {
                "id": PORTFOLIO_ID,
                "balance": fields.get("balance"),
                "peak_balance": fields.get("peak_balance"),
                "trade_count": fields.get("trade_count"),
                "paused": fields.get("paused"),
                "max_drawdown_bps": fields.get("max_drawdown_bps"),
                "daily_volume_limit": fields.get("daily_volume_limit"),
                "cooldown_ms": fields.get("cooldown_ms"),
                "total_traded_today": fields.get("total_traded_today"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Execute trade ────────────────────────────────────────


class TradeRequest(BaseModel):
    amount: int
    min_output: int
    quantum_score: Optional[int] = 0
    is_quantum_optimized: Optional[bool] = True
    qubo_solution_data: Optional[str] = None
    protocol_address: Optional[str] = None  # target DEX/protocol address


@app.post("/api/trade")
async def trade(req: TradeRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    if req.min_output < 0:
        raise HTTPException(status_code=400, detail="min_output must be >= 0")

    # Protocol whitelist check
    check_protocol_whitelist(req.protocol_address)

    logger.info(
        f" Trade request: {req.amount} MIST, "
        f"min_output={req.min_output}, q_score={req.quantum_score}"
    )

    try:
        cmd = build_swap_and_rebalance(
            amount_mist=req.amount,
            min_output=req.min_output,
            is_quantum_optimized=req.is_quantum_optimized,
            quantum_optimization_score=req.quantum_score,
        )
        result = _run_sui_cmd(cmd)

        if not result.success:
            parsed = parse_abort_error(result.error)
            status_code = 422 if parsed.is_move_abort else 500
            raise HTTPException(status_code=status_code, detail=error_response_body(result.error))

        logger.info(f" TX {result.digest} — status: {result.status}")

        # If QUBO solution data provided, also log a quantum audit receipt
        if req.qubo_solution_data:
            proof_hash = hashlib.sha256(req.qubo_solution_data.encode()).digest()
            audit_cmd = build_log_execution(proof_hash, req.amount, req.quantum_score)
            _run_sui_cmd(audit_cmd)

        return {
            "success": True,
            "digest": result.digest,
            "status": result.status,
            "events": result.events,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Trade", e)
        parsed = parse_abort_error(e)
        status_code = 422 if parsed.is_move_abort else 500
        raise HTTPException(status_code=status_code, detail=error_response_body(e))


# ── Log quantum audit proof ─────────────────────────────


class AuditRequest(BaseModel):
    proof_data: str
    amount: Optional[int] = 0
    quantum_score: Optional[int] = 0


@app.post("/api/audit")
async def audit(req: AuditRequest):
    if not req.proof_data:
        raise HTTPException(status_code=400, detail="proof_data is required")

    try:
        proof_hash = hashlib.sha256(req.proof_data.encode()).digest()
        cmd = build_log_execution(proof_hash, req.amount, req.quantum_score)
        result = _run_sui_cmd(cmd)

        if not result.success:
            raise HTTPException(status_code=500, detail=error_response_body(result.error))

        logger.info(f" Audit TX: {result.digest}")

        return {
            "success": True,
            "digest": result.digest,
            "proof_hash_hex": proof_hash.hex(),
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Audit", e)
        raise HTTPException(status_code=500, detail=error_response_body(e))


# ── Atomic rebalance ────────────────────────────────────


class AtomicRebalanceRequest(BaseModel):
    swap_amounts: List[int]
    swap_min_outputs: List[int]
    quantum_score: Optional[int] = 0
    is_quantum_optimized: Optional[bool] = True
    qubo_solution_data: Optional[str] = None


@app.post("/api/atomic-rebalance")
async def atomic_rebalance(req: AtomicRebalanceRequest):
    if not req.swap_amounts:
        raise HTTPException(status_code=400, detail="swap_amounts must be a non-empty array")
    if len(req.swap_amounts) != len(req.swap_min_outputs):
        raise HTTPException(
            status_code=400,
            detail="swap_amounts and swap_min_outputs must be same length",
        )

    logger.info(
        f" Atomic rebalance: {len(req.swap_amounts)} swaps, "
        f"total={sum(req.swap_amounts)} MIST"
    )

    try:
        cmd = build_atomic_rebalance(
            swap_amounts=req.swap_amounts,
            swap_min_outputs=req.swap_min_outputs,
            is_quantum_optimized=req.is_quantum_optimized,
            quantum_optimization_score=req.quantum_score,
        )
        result = _run_sui_cmd(cmd)

        if not result.success:
            parsed = parse_abort_error(result.error)
            status_code = 422 if parsed.is_move_abort else 500
            raise HTTPException(status_code=status_code, detail=error_response_body(result.error))

        logger.info(f" Atomic rebalance TX {result.digest} — status: {result.status}")

        # Optional audit proof
        if req.qubo_solution_data:
            proof_hash = hashlib.sha256(req.qubo_solution_data.encode()).digest()
            total_amount = sum(req.swap_amounts)
            audit_cmd = build_log_execution(proof_hash, total_amount, req.quantum_score)
            _run_sui_cmd(audit_cmd)

        return {
            "success": True,
            "digest": result.digest,
            "status": result.status,
            "num_swaps": len(req.swap_amounts),
            "events": result.events,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("AtomicRebalance", e)
        parsed = parse_abort_error(e)
        status_code = 422 if parsed.is_move_abort else 500
        raise HTTPException(status_code=status_code, detail=error_response_body(e))


# ── Oracle-validated swap ────────────────────────────────


class OracleSwapRequest(BaseModel):
    amount: int
    min_output: int
    oracle_price_x8: int
    expected_price_x8: int
    oracle_timestamp_ms: int
    asset_symbol: str
    quantum_score: Optional[int] = 0
    is_quantum_optimized: Optional[bool] = True


@app.post("/api/oracle-swap")
async def oracle_swap(req: OracleSwapRequest):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="amount must be > 0")
    if not req.oracle_price_x8 or not req.expected_price_x8:
        raise HTTPException(
            status_code=400,
            detail="oracle_price_x8 and expected_price_x8 required",
        )
    if not ORACLE_CONFIG_ID:
        raise HTTPException(status_code=500, detail="ORACLE_CONFIG_ID not configured")

    logger.info(
        f" Oracle swap: {req.amount} MIST, "
        f"oracle=${req.oracle_price_x8 / 1e8:.4f}, "
        f"expected=${req.expected_price_x8 / 1e8:.4f}"
    )

    try:
        cmd = build_oracle_validated_swap(
            amount_mist=req.amount,
            min_output=req.min_output,
            oracle_price_x8=req.oracle_price_x8,
            expected_price_x8=req.expected_price_x8,
            oracle_timestamp_ms=req.oracle_timestamp_ms,
            asset_symbol=req.asset_symbol,
            is_quantum_optimized=req.is_quantum_optimized,
            quantum_optimization_score=req.quantum_score,
        )
        result = _run_sui_cmd(cmd)

        if not result.success:
            parsed = parse_abort_error(result.error)
            status_code = 422 if parsed.is_move_abort else 500
            raise HTTPException(status_code=status_code, detail=error_response_body(result.error))

        logger.info(f" Oracle swap TX {result.digest} — status: {result.status}")

        return {
            "success": True,
            "digest": result.digest,
            "status": result.status,
            "events": result.events,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("OracleSwap", e)
        parsed = parse_abort_error(e)
        status_code = 422 if parsed.is_move_abort else 500
        raise HTTPException(status_code=status_code, detail=error_response_body(e))


# ── Emergency pause (admin only) ─────────────────────────


class PauseRequest(BaseModel):
    paused: Optional[bool] = True


@app.get("/api/whitelist")
async def get_whitelist():
    """Return the current protocol whitelist."""
    return {
        "whitelist": list(PROTOCOL_WHITELIST),
        "mode": "permissive" if not PROTOCOL_WHITELIST else "enforced",
    }


class WhitelistRequest(BaseModel):
    protocol_address: str
    action: str = "add"  # "add" or "remove"


@app.post("/api/whitelist")
async def manage_whitelist(req: WhitelistRequest):
    """Add or remove a protocol from the backend whitelist."""
    if not ADMIN_CAP_ID:
        raise HTTPException(status_code=403, detail="Admin key not configured")
    if req.action == "add":
        PROTOCOL_WHITELIST.add(req.protocol_address)
        logger.info(f" Added {req.protocol_address} to protocol whitelist")
    elif req.action == "remove":
        PROTOCOL_WHITELIST.discard(req.protocol_address)
        logger.info(f" Removed {req.protocol_address} from protocol whitelist")
    else:
        raise HTTPException(status_code=400, detail="action must be 'add' or 'remove'")
    return {"whitelist": list(PROTOCOL_WHITELIST), "action": req.action}


@app.post("/api/pause")
async def pause(req: PauseRequest):
    if not ADMIN_CAP_ID:
        raise HTTPException(status_code=403, detail="Admin key not configured on this relayer")

    try:
        cmd = build_set_paused(req.paused)
        result = _run_sui_cmd(cmd)

        if not result.success:
            raise HTTPException(status_code=500, detail=error_response_body(result.error))

        label = "PAUSED" if req.paused else "RESUMED"
        logger.info(f"{label} TX: {result.digest}")

        return {
            "success": True,
            "digest": result.digest,
            "paused": req.paused,
        }

    except HTTPException:
        raise
    except Exception as e:
        log_error("Pause", e)
        raise HTTPException(status_code=500, detail=error_response_body(e))


# ═══════════════════════════════════════════════════════════
#  START
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    print(f"\n Relayer server running on http://localhost:{PORT}")
    print(f"   Network:    {NETWORK}")
    print(f"   Package:    {PACKAGE_ID}")
    print(f"   Portfolio:  {PORTFOLIO_ID}")
    print(f"\n   Endpoints:")
    print(f"     POST /api/trade             — Execute quantum-optimized trade")
    print(f"     POST /api/atomic-rebalance  — Multi-swap atomic rebalance")
    print(f"     POST /api/oracle-swap       — Oracle-validated swap")
    print(f"     POST /api/audit             — Log quantum proof on-chain")
    print(f"     POST /api/pause             — Emergency kill-switch")
    print(f"     GET  /api/status            — Portfolio & gas status")
    print(f"     GET  /api/health            — Health check\n")

    uvicorn.run(app, host="0.0.0.0", port=PORT)
