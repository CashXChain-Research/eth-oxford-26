#!/usr/bin/env python3
"""
event_provider.py — Live Event Feeder for the Frontend Dashboard

Subscribes to ALL quantum_vault on-chain events and:
  1. Logs them as structured JSON to stdout
  2. Pushes them to connected WebSocket clients in real-time

Frontend connects to ws://localhost:3002 and receives JSON events.

Usage:
    python event_provider.py
"""

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, Set

import httpx
import websockets
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

NETWORK = os.getenv("SUI_NETWORK", "devnet")
RPC_URL = os.getenv("SUI_RPC_URL", f"https://fullnode.{NETWORK}.sui.io:443")
PACKAGE_ID = os.getenv("PACKAGE_ID", "")
WS_PORT = int(os.getenv("WS_PORT", "3002"))
POLL_INTERVAL_MS = int(os.getenv("EVENT_POLL_INTERVAL", "3000"))

# All event types we care about
EVENT_TYPES = [
    f"{PACKAGE_ID}::portfolio::TradeEvent",
    f"{PACKAGE_ID}::portfolio::QuantumTradeEvent",
    f"{PACKAGE_ID}::portfolio::GuardrailTriggered",
    f"{PACKAGE_ID}::portfolio::RebalanceResultCreated",
    f"{PACKAGE_ID}::portfolio::MockSwapExecuted",
    f"{PACKAGE_ID}::portfolio::PausedChanged",
    f"{PACKAGE_ID}::portfolio::Deposited",
    f"{PACKAGE_ID}::portfolio::Withdrawn",
    f"{PACKAGE_ID}::portfolio::LimitsUpdated",
    f"{PACKAGE_ID}::portfolio::AgentFrozenEvt",
    f"{PACKAGE_ID}::portfolio::AgentUnfrozenEvt",
    f"{PACKAGE_ID}::portfolio::PortfolioCreated",
    f"{PACKAGE_ID}::portfolio::AtomicRebalanceCompleted",
    f"{PACKAGE_ID}::portfolio::OracleSwapExecuted",
    f"{PACKAGE_ID}::oracle::OracleConfigCreated",
    f"{PACKAGE_ID}::oracle::OracleConfigUpdated",
    f"{PACKAGE_ID}::oracle::OracleValidationPassed",
    f"{PACKAGE_ID}::oracle::OracleValidationFailed",
    f"{PACKAGE_ID}::audit_trail::QuantumAuditCreated",
    f"{PACKAGE_ID}::audit_trail::AuditReceiptCreated",
]

# ═══════════════════════════════════════════════════════════
#  WEBSOCKET SERVER
# ═══════════════════════════════════════════════════════════

ws_clients: Set[websockets.WebSocketServerProtocol] = set()


async def ws_handler(websocket: websockets.WebSocketServerProtocol):
    """Handle a new WebSocket connection."""
    ws_clients.add(websocket)
    print(f" WebSocket client connected (total: {len(ws_clients)})")

    try:
        await websocket.send(
            json.dumps(
                {
                    "type": "system::Connected",
                    "data": {
                        "message": "Connected to quantum_vault event stream",
                        "eventTypes": len(EVENT_TYPES),
                    },
                    "timestamp": str(int(time.time() * 1000)),
                }
            )
        )

        # Keep connection alive
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        ws_clients.discard(websocket)
        print(f" WebSocket client disconnected (total: {len(ws_clients)})")


async def broadcast_event(structured: dict):
    """Broadcast a structured event to ALL connected WebSocket clients."""
    if not ws_clients:
        return
    payload = json.dumps(structured)
    await asyncio.gather(
        *(client.send(payload) for client in ws_clients if client.open),
        return_exceptions=True,
    )


# ═══════════════════════════════════════════════════════════
#  FORMATTERS
# ═══════════════════════════════════════════════════════════


def format_event(event_type: str, data: Dict[str, Any]) -> str:
    """Format an on-chain event for console output."""
    parts = event_type.split("::")
    short_type = "::".join(parts[1:]) if len(parts) > 1 else event_type

    if short_type == "portfolio::TradeEvent":
        return "\n".join(
            [
                f" Trade #{data.get('trade_id', '?')}",
                f"   Agent:    {data.get('agent_address', '?')}",
                f"   Amount:   {data.get('input_amount', '?')} → {data.get('output_amount', '?')} MIST",
                f"   Balance:  {data.get('balance_before', '?')} → {data.get('balance_after', '?')}",
                f"   Quantum:  {'  YES' if data.get('is_quantum_optimized') else ' NO'}",
            ]
        )

    if short_type == "portfolio::QuantumTradeEvent":
        return "\n".join(
            [
                f"  Quantum Trade #{data.get('trade_id', '?')}",
                f"   Agent:    {data.get('agent_address', '?')}",
                f"   Amount:   {data.get('input_amount', '?')} → {data.get('output_amount', '?')} MIST",
                f"   Balance:  {data.get('balance_before', '?')} → {data.get('balance_after', '?')}",
                f"   Q-Score:  {data.get('quantum_optimization_score', '?')}/100",
                f"   Quantum:  {'  VERIFIED' if data.get('is_quantum_optimized') else ' NO'}",
            ]
        )

    if short_type == "portfolio::GuardrailTriggered":
        return "\n".join(
            [
                " GUARDRAIL BLOCKED",
                f"   Agent:     {data.get('agent', '?')}",
                f"   Reason:    {data.get('reason', '?')}",
                f"   Requested: {data.get('requested_amount', '?')} MIST",
                f"   Vault:     {data.get('vault_balance', '?')} MIST",
            ]
        )

    if short_type == "portfolio::PausedChanged":
        if data.get("paused"):
            return " PORTFOLIO PAUSED — all trades blocked"
        return "▶  PORTFOLIO RESUMED — trades allowed"

    if short_type == "audit_trail::QuantumAuditCreated":
        return "\n".join(
            [
                " Quantum Audit Proof",
                f"   Receipt:  {data.get('receipt_id', '?')}",
                f"   Agent:    {data.get('agent_address', '?')}",
                f"   Amount:   {data.get('executed_amount', '?')} MIST",
                f"   Q-Score:  {data.get('quantum_score', '?')}/100",
                f"   Proof:    {data.get('quantum_proof_hash', '?')}",
            ]
        )

    if short_type == "portfolio::Deposited":
        return (
            f" Deposited {data.get('amount', '?')} MIST → balance: {data.get('new_balance', '?')}"
        )

    if short_type == "portfolio::Withdrawn":
        return (
            f" Withdrawn {data.get('amount', '?')} MIST → remaining: {data.get('remaining', '?')}"
        )

    if short_type == "portfolio::RebalanceResultCreated":
        return "\n".join(
            [
                " Rebalance Result",
                f"   Result ID: {data.get('result_id', '?')}",
                f"   Success:   {' YES' if data.get('success') else ' NO'}",
                f"   Q-Energy:  {data.get('quantum_energy', '?')}",
                f"   Trade #:   {data.get('trade_id', '?')}",
            ]
        )

    if short_type == "portfolio::MockSwapExecuted":
        return "\n".join(
            [
                " Mock Swap",
                f"   Agent:    {data.get('agent_address', '?')}",
                f"   Input:    {data.get('input_amount', '?')} MIST",
                f"   Output:   {data.get('mock_output', '?')} MIST",
                f"   Slippage: {data.get('slippage_bps', '?')} bps",
            ]
        )

    if short_type == "portfolio::AtomicRebalanceCompleted":
        return "\n".join(
            [
                " Atomic Rebalance Complete",
                f"   Agent:       {data.get('agent_address', '?')}",
                f"   Swaps:       {data.get('num_swaps', '?')}",
                f"   Total In:    {data.get('total_input', '?')} MIST",
                f"   Total Out:   {data.get('total_output', '?')} MIST",
                f"   Balance:     {data.get('balance_before', '?')} → {data.get('balance_after', '?')}",
                f"   Max Slippage: {data.get('max_slippage_bps', '?')} bps",
            ]
        )

    if short_type == "portfolio::OracleSwapExecuted":
        oracle_price = data.get("oracle_price_x8", 0)
        expected_price = data.get("expected_price_x8", 0)
        return "\n".join(
            [
                " Oracle-Validated Swap",
                f"   Agent:    {data.get('agent_address', '?')}",
                f"   Amount:   {data.get('amount', '?')} MIST",
                f"   Oracle:   ${oracle_price / 1e8:.4f}",
                f"   Expected: ${expected_price / 1e8:.4f}",
                f"   Slippage: {data.get('slippage_bps', '?')} bps",
            ]
        )

    if short_type == "oracle::OracleValidationPassed":
        oracle_price = data.get("oracle_price_x8", 0)
        expected_price = data.get("expected_price_x8", 0)
        return "\n".join(
            [
                " Oracle Validation Passed",
                f"   Asset:    {data.get('asset_symbol', '?')}",
                f"   Oracle:   ${oracle_price / 1e8:.4f}",
                f"   Expected: ${expected_price / 1e8:.4f}",
                f"   Slippage: {data.get('slippage_bps', '?')}/{data.get('max_allowed_bps', '?')} bps",
            ]
        )

    if short_type == "oracle::OracleValidationFailed":
        oracle_price = data.get("oracle_price_x8", 0)
        expected_price = data.get("expected_price_x8", 0)
        return "\n".join(
            [
                " Oracle Validation FAILED",
                f"   Asset:    {data.get('asset_symbol', '?')}",
                f"   Oracle:   ${oracle_price / 1e8:.4f}",
                f"   Expected: ${expected_price / 1e8:.4f}",
                f"   Slippage: {data.get('slippage_bps', '?')}/{data.get('max_allowed_bps', '?')} bps",
                f"   Reason:   {data.get('reason', '?')}",
            ]
        )

    # Default
    return f" {short_type}: {json.dumps(data)}"


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
#  POLL-BASED EVENT WATCHER
# ═══════════════════════════════════════════════════════════

seen_events: Set[str] = set()


async def poll_events():
    """Poll for new events from all tracked event types."""
    for event_type in EVENT_TYPES:
        try:
            result = _rpc_call(
                "suix_queryEvents",
                [
                    {"MoveEventType": event_type},
                    None,
                    5,
                    True,  # descending
                ],
            )
            events = result.get("data", [])

            for ev in events:
                ev_id = ev.get("id", {})
                ev_key = f"{ev_id.get('txDigest', '')}:{ev_id.get('eventSeq', '')}"
                if ev_key in seen_events:
                    continue
                seen_events.add(ev_key)

                ts_ms = int(ev.get("timestampMs", "0"))
                from datetime import datetime, timezone

                ts_str = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).isoformat()

                parsed_json = ev.get("parsedJson", {})
                ev_type = ev.get("type", "")

                print(f"\n[{ts_str}]")
                print(format_event(ev_type, parsed_json))
                print(f"   TX: {ev_id.get('txDigest', '?')}")

                # Build structured JSON for frontend
                parts = ev_type.split("::")
                short_type = "::".join(parts[1:]) if len(parts) > 1 else ev_type
                structured = {
                    "type": short_type,
                    "data": parsed_json,
                    "timestamp": ev.get("timestampMs"),
                    "digest": ev_id.get("txDigest"),
                }

                # Write to stdout as JSON
                print(f"\nEVENT_JSON:{json.dumps(structured)}")
                # Push to WebSocket clients
                await broadcast_event(structured)

        except Exception:
            # Ignore query errors for event types that don't exist yet
            pass


# ═══════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════


async def poll_loop():
    """Continuously poll for events."""
    interval = POLL_INTERVAL_MS / 1000
    # Initial fetch
    await poll_events()
    while True:
        await asyncio.sleep(interval)
        await poll_events()


async def main():
    print("═══════════════════════════════════════════════════")
    print("   quantum_vault Event Provider")
    print("  Data source for the frontend dashboard")
    print("═══════════════════════════════════════════════════")
    print(f"  Network:    {NETWORK}")
    print(f"  RPC:        {RPC_URL}")
    print(f"  Package:    {PACKAGE_ID}")
    print(f"  Events:     {len(EVENT_TYPES)} types")
    print(f"  Poll:       {POLL_INTERVAL_MS}ms")
    print(f"  WebSocket:  ws://localhost:{WS_PORT}")
    print()

    # Start WebSocket server
    async with websockets.serve(ws_handler, "0.0.0.0", WS_PORT):
        print(f"   WebSocket server running on ws://localhost:{WS_PORT}\n")
        # Run poll loop alongside WebSocket server
        await poll_loop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Stopping event provider...")
