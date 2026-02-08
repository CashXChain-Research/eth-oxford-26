#!/usr/bin/env python3
"""
agent_executor.py — AI Agent Backend CLI

Builds and executes Programmable Transaction Blocks (PTBs)
against the quantum_vault smart contracts on Sui.

Usage:
    python agent_executor.py demo [amount_mist]
    python agent_executor.py swap [amount_mist]
    python agent_executor.py quantum [amount_mist] [min_output] [quantum_score]
    python agent_executor.py dryrun [amount_mist]
    python agent_executor.py killswitch
    python agent_executor.py pause
    python agent_executor.py resume
    python agent_executor.py stream
"""

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict

import httpx
from dotenv import load_dotenv

from core.error_map import parse_abort_error
from blockchain.ptb_builder import (
    TxResult,
    _run_sui_cmd,
    build_execute_rebalance,
    build_set_paused,
    build_swap_and_rebalance,
    dry_run_rebalance,
    dry_run_swap,
    execute_rebalance,
    execute_set_paused,
    execute_swap_and_rebalance,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

NETWORK = os.getenv("SUI_NETWORK", "devnet")
RPC_URL = os.getenv("SUI_RPC_URL", f"https://fullnode.{NETWORK}.sui.io:443")
PACKAGE_ID = os.getenv("PACKAGE_ID", "")
PORTFOLIO_ID = os.getenv("PORTFOLIO_ID", os.getenv("PORTFOLIO_OBJECT_ID", ""))
AGENT_CAP_ID = os.getenv("AGENT_CAP_ID", "")

_rpc_id = 0


def _rpc_call(method: str, params: list) -> dict:
    global _rpc_id
    _rpc_id += 1
    payload = {"jsonrpc": "2.0", "id": _rpc_id, "method": method, "params": params}
    with httpx.Client(timeout=15) as client:
        resp = client.post(RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result", {})


def _get_portfolio_balance() -> int:
    """Fetch current portfolio balance in MIST."""
    obj = _rpc_call(
        "sui_getObject",
        [
            PORTFOLIO_ID,
            {"showContent": True},
        ],
    )
    fields = obj.get("data", {}).get("content", {}).get("fields", {})
    return int(fields.get("balance", "0"))


# ═══════════════════════════════════════════════════════════
#  COMMANDS
# ═══════════════════════════════════════════════════════════


def cmd_demo(amount: int):
    """Demo rebalance — calls execute_rebalance (no fund movement)."""
    print(f"\n Demo rebalance: {amount} MIST")
    result = execute_rebalance(amount, True)
    if result.success:
        print(f" TX digest: {result.digest}")
        for ev in result.events:
            print(f"   {ev['type']}: {json.dumps(ev['data'], indent=2)}")
    else:
        print(f" Failed: {result.error}")


def cmd_swap(amount: int):
    """Swap rebalance — withdraw → DEX swap → deposit back."""
    print(f"\n Swap rebalance: {amount} MIST")
    result = execute_swap_and_rebalance(amount, 0, True, 0)
    if result.success:
        print(f" Swap TX digest: {result.digest}")
        for ev in result.events:
            print(f"   {ev['type']}: {json.dumps(ev['data'], indent=2)}")
    else:
        print(f" Failed: {result.error}")


def cmd_quantum(amount: int, min_output: int, quantum_score: int):
    """Quantum swap_and_rebalance with score."""
    print(f"\n  Quantum swap_and_rebalance: {amount} MIST")
    result = execute_swap_and_rebalance(amount, min_output, True, quantum_score)
    if result.success:
        print(f" Quantum TX: {result.digest}")
        for ev in result.events:
            print(f"   {ev['type']}: {json.dumps(ev['data'], indent=2)}")
    else:
        print(f" Failed: {result.error}")


def cmd_dryrun(amount: int):
    """Dry-run a transaction WITHOUT submitting."""
    print(f"\n Dry-run: {amount} MIST")
    result = dry_run_rebalance(amount, True)
    if result.success:
        print(" Dry-run PASSED — guardrails OK")
    else:
        parsed = parse_abort_error(result.error)
        print(f" Dry-run BLOCKED: {parsed.frontend_message}")


def cmd_killswitch():
    """Fat Finger test: try to trade 100% of portfolio."""
    print("\n KILL-SWITCH TEST: attempting 100% portfolio drain...")
    try:
        balance = _get_portfolio_balance()
        print(f"   Portfolio balance: {balance} MIST")
        print(f"   Attempting trade:  {balance} MIST (100%)")

        result = dry_run_rebalance(balance, False)
        if result.success:
            print("  Trade would PASS — check your guardrails!")
        else:
            parsed = parse_abort_error(result.error)
            print(f"  BLOCKED by guardrails: {parsed.frontend_message}")
            print(" Kill-switch working! Portfolio is safe.")
    except Exception as e:
        print(f" Error: {e}")


def cmd_pause():
    """Emergency pause."""
    print("\n Pausing portfolio...")
    result = execute_set_paused(True)
    if result.success:
        print(f" PAUSED — TX: {result.digest}")
    else:
        print(f" Failed: {result.error}")


def cmd_resume():
    """Resume from pause."""
    print("\n▶  Resuming portfolio...")
    result = execute_set_paused(False)
    if result.success:
        print(f"▶  RESUMED — TX: {result.digest}")
    else:
        print(f" Failed: {result.error}")


def cmd_stream():
    """Stream TradeEvents from the chain (poll-based)."""
    print(" Streaming TradeEvent...")
    print("   Press Ctrl+C to stop\n")

    event_type = f"{PACKAGE_ID}::portfolio::TradeEvent"
    seen = set()

    try:
        while True:
            try:
                result = _rpc_call(
                    "suix_queryEvents",
                    [
                        {"MoveEventType": event_type},
                        None,
                        5,
                        True,
                    ],
                )
                events = result.get("data", [])
                for ev in events:
                    ev_id = ev.get("id", {})
                    key = f"{ev_id.get('txDigest')}:{ev_id.get('eventSeq')}"
                    if key in seen:
                        continue
                    seen.add(key)

                    d = ev.get("parsedJson", {})
                    print(f"\n Trade #{d.get('trade_id', '?')}")
                    print(f"   Agent:    {d.get('agent_address', '?')}")
                    print(f"   Amount:   {d.get('input_amount', '?')} MIST")
                    print(
                        f"   Balance:  {d.get('balance_before', '?')} → {d.get('balance_after', '?')}"
                    )
                    is_q = d.get("is_quantum_optimized", False)
                    print(f"   Quantum:  {'  YES' if is_q else ' NO'}")
            except Exception:
                pass

            time.sleep(3)
    except KeyboardInterrupt:
        print("\n Stopped.")


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════


def main():
    print(f" Network: {NETWORK} ({RPC_URL})")
    print(f" Package: {PACKAGE_ID}")

    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    amount = int(sys.argv[2]) if len(sys.argv) > 2 else 1_000_000_000  # default 1 SUI

    if cmd == "demo":
        cmd_demo(amount)
    elif cmd == "swap":
        cmd_swap(amount)
    elif cmd == "quantum":
        min_out = int(sys.argv[3]) if len(sys.argv) > 3 else int(amount * 0.9)
        q_score = int(sys.argv[4]) if len(sys.argv) > 4 else 85
        cmd_quantum(amount, min_out, q_score)
    elif cmd == "pause":
        cmd_pause()
    elif cmd == "resume":
        cmd_resume()
    elif cmd == "dryrun":
        cmd_dryrun(amount)
    elif cmd == "killswitch":
        cmd_killswitch()
    elif cmd == "stream":
        cmd_stream()
    else:
        print(
            "Usage: python agent_executor.py "
            "<demo|swap|quantum|dryrun|killswitch|pause|resume|stream> "
            "[amount_mist] [min_output] [quantum_score]"
        )


if __name__ == "__main__":
    main()
