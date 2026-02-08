#!/usr/bin/env python3
"""
Safety Tests — Guardrail validation and attack demonstrations.

Combines:
  - Kill-switch test: Fat-finger protection, cooldown validation
  - Redline tests: Tries to break all guardrails (5 safety scenarios)
  - Attack demo: Risk agent validation against 5 attack vectors
"""

import inspect
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

import httpx
import numpy as np
from dotenv import load_dotenv

from agents.manager import (
    PipelineState,
    dict_to_state,
    risk_agent,
    run_pipeline,
    state_to_dict,
)
from blockchain.ptb_builder import (
    TxResult,
    _run_sui_cmd,
    build_execute_rebalance,
    build_swap_and_rebalance,
    dry_run_rebalance,
    dry_run_swap,
    execute_rebalance,
    execute_swap_and_rebalance,
)
from core.error_map import ERROR_MAP, parse_abort_error
from quantum.optimizer import Asset, OptimizationResult, PortfolioQUBO, QUBOConfig

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")

# ===== Configuration =====

NETWORK = os.getenv("SUI_NETWORK", "devnet")
RPC_URL = os.getenv("SUI_RPC_URL", f"https://fullnode.{NETWORK}.sui.io:443")
PACKAGE_ID = os.getenv("PACKAGE_ID", "")
PORTFOLIO_ID = os.getenv("PORTFOLIO_ID", os.getenv("PORTFOLIO_OBJECT_ID", ""))

_rpc_id = 0

ERROR_NAMES = {
    0: "EInvalidAgent",
    1: "EAgentFrozen",
    2: "ECooldownActive",
    3: "EVolumeExceeded",
    4: "EDrawdownExceeded",
    5: "EInsufficientBalance",
    6: "EPaused",
    7: "ESlippageExceeded",
}


# ===== RPC Helpers =====

def _rpc_call(method: str, params: list) -> dict:
    """Execute RPC call to Sui node."""
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
    """Fetch current portfolio balance."""
    obj = _rpc_call("sui_getObject", [PORTFOLIO_ID, {"showContent": True}])
    fields = obj.get("data", {}).get("content", {}).get("fields", {})
    return int(fields.get("balance", "0"))


def _get_portfolio_fields() -> dict:
    """Fetch all portfolio fields."""
    obj = _rpc_call("sui_getObject", [PORTFOLIO_ID, {"showContent": True}])
    return obj.get("data", {}).get("content", {}).get("fields", {})


# ===== Test Result Type =====

@dataclass
class TestResult:
    """Single test result."""
    name: str
    passed: bool
    error: Optional[str] = None
    abort_code: Optional[int] = None
    detail: Optional[str] = None


def _print_result(r: TestResult):
    """Print test result with icon."""
    icon = "PASS" if r.passed else "FAIL"
    print(f"  [{icon}] {r.name}")
    if r.detail:
        print(f"       {r.detail}")
    if r.error and not r.passed:
        print(f"       Error: {r.error[:100]}")
    print()


# ===== Part 1: Kill-Switch Tests =====

def kill_switch_test_safe_trade() -> TestResult:
    """Test 1: Small safe trade (should PASS)."""
    print("Kill-Switch Test 1: Safe Trade (5% of vault)")
    balance = _get_portfolio_balance()
    safe_amount = int(balance * 0.05)

    result = dry_run_rebalance(safe_amount, True)
    passed = result.success

    return TestResult(
        name="Safe Trade (5%)",
        passed=passed,
        detail=f"{safe_amount} MIST allowed" if passed else "Trade blocked unexpectedly",
        error=result.error if not result.success else None,
    )


def kill_switch_test_fat_finger() -> TestResult:
    """Test 2: Fat-finger 100% drain (should BLOCK with EDrawdownExceeded)."""
    print("Kill-Switch Test 2: Fat Finger (100% drain)")
    balance = _get_portfolio_balance()

    result = dry_run_rebalance(balance, True)
    passed = not result.success

    abort_code = None
    if not result.success:
        parsed = parse_abort_error(result.error)
        abort_code = parsed.code

    return TestResult(
        name="Fat Finger (100%)",
        passed=passed,
        detail=f"Correctly blocked with {ERROR_NAMES.get(abort_code, 'unknown')}",
        abort_code=abort_code,
        error=result.error,
    )


def kill_switch_test_cooldown() -> TestResult:
    """Test 3: Rapid-fire trades (should BLOCK with ECooldownActive)."""
    print("Kill-Switch Test 3: Cooldown Violation")
    balance = _get_portfolio_balance()
    safe_amount = int(balance * 0.05)

    try:
        # Execute first trade
        result1 = execute_rebalance(safe_amount, True)
        if not result1.success:
            return TestResult(
                name="Cooldown (rapid-fire)",
                passed=False,
                detail="Could not execute first trade",
                error=result1.error,
            )

        # Immediately try second trade
        result2 = dry_run_rebalance(safe_amount, True)
        passed = not result2.success

        abort_code = None
        if not result2.success:
            parsed = parse_abort_error(result2.error)
            abort_code = parsed.code

        return TestResult(
            name="Cooldown (rapid-fire)",
            passed=passed,
            detail=f"Second trade blocked with {ERROR_NAMES.get(abort_code, 'unknown')}",
            abort_code=abort_code,
            error=result2.error,
        )
    except Exception as e:
        return TestResult(
            name="Cooldown (rapid-fire)",
            passed=False,
            detail="Test requires funded account",
            error=str(e)[:100],
        )


# ===== Part 2: Redline Tests =====

def redline_test_drawdown() -> TestResult:
    """Test 4: 50% portfolio drain (EDrawdownExceeded)."""
    print("Redline Test 1: Drawdown Exceeded (50%)")
    balance = _get_portfolio_balance()
    drain_amount = int(balance * 0.5)

    result = dry_run_swap(drain_amount, 0, 0)
    passed = not result.success and (
        parse_abort_error(result.error).code == 4
    )

    abort_code = parse_abort_error(result.error).code if not result.success else None

    return TestResult(
        name="Drawdown (50% drain)",
        passed=passed,
        detail=f"Code {abort_code}: {ERROR_NAMES.get(abort_code, 'unknown')}",
        abort_code=abort_code,
        error=result.error,
    )


def redline_test_slippage() -> TestResult:
    """Test 5: Impossible slippage (ESlippageExceeded)."""
    print("Redline Test 2: Slippage Exceeded")
    amount = 100_000_000
    min_output = 10_000_000_000  # impossible

    result = dry_run_swap(amount, min_output, 0)
    passed = not result.success and (
        parse_abort_error(result.error).code == 7
    )

    abort_code = parse_abort_error(result.error).code if not result.success else None

    return TestResult(
        name="Slippage (min_output impossible)",
        passed=passed,
        detail=f"Code {abort_code}: {ERROR_NAMES.get(abort_code, 'unknown')}",
        abort_code=abort_code,
        error=result.error,
    )


def redline_test_insufficient_balance() -> TestResult:
    """Test 6: Trade more than balance (EInsufficientBalance)."""
    print("Redline Test 3: Insufficient Balance")
    balance = _get_portfolio_balance()
    over_amount = balance + 1_000_000_000

    result = dry_run_swap(over_amount, 0, 0)
    passed = not result.success and (
        parse_abort_error(result.error).code in (4, 5)
    )

    abort_code = parse_abort_error(result.error).code if not result.success else None

    return TestResult(
        name="Insufficient Balance (trade > vault)",
        passed=passed,
        detail=f"Code {abort_code}: {ERROR_NAMES.get(abort_code, 'unknown')}",
        abort_code=abort_code,
        error=result.error,
    )


def redline_test_100percent_drain() -> TestResult:
    """Test 7: 100% portfolio drain (ultimate fat-finger)."""
    print("Redline Test 4: 100% Drain")
    balance = _get_portfolio_balance()

    result = dry_run_swap(balance, 0, 0)
    passed = not result.success and (
        parse_abort_error(result.error).code in (2, 4)
    )

    abort_code = parse_abort_error(result.error).code if not result.success else None

    return TestResult(
        name="100% Portfolio Drain",
        passed=passed,
        detail=f"Code {abort_code}: {ERROR_NAMES.get(abort_code, 'unknown')}",
        abort_code=abort_code,
        error=result.error,
    )


# ===== Part 3: Attack Demo (Risk Agent) =====

def _run_risk_check(opt_result: OptimizationResult) -> dict:
    """Push optimization result through RiskAgent."""
    state = PipelineState()
    state.optimization_result = opt_result
    state_dict = state_to_dict(state)
    result_dict = risk_agent(state_dict)
    final = dict_to_state(result_dict)
    return {
        "status": final.status,
        "approved": final.risk_approved,
        "checks": final.risk_checks,
        "report": final.risk_report,
        "logs": final.logs,
    }


def attack_concentrated_position() -> TestResult:
    """Attack 1: 100% in single asset (should BLOCK)."""
    print("Attack Test 1: Concentrated Position (100% SUI)")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 0, "BTC": 0, "SOL": 0, "AVAX": 0},
        energy=-1.0,
        weights={"SUI": 1.0, "ETH": 0.0, "BTC": 0.0, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.35,
        expected_risk=0.40,
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = _run_risk_check(result)
    passed = not r["approved"]

    failed_checks = [k for k, v in r["checks"].items() if not v]

    return TestResult(
        name="Concentrated Position (100% SUI)",
        passed=passed,
        detail=f"Blocked" if passed else "LEAKED THROUGH",
    )


def attack_extreme_risk() -> TestResult:
    """Attack 2: Extreme risk (σ > 35%, should BLOCK)."""
    print("Attack Test 2: Extreme Risk (σ = 80%)")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 1, "BTC": 0, "SOL": 1, "AVAX": 0},
        energy=-2.0,
        weights={"SUI": 0.33, "ETH": 0.33, "BTC": 0.0, "SOL": 0.34, "AVAX": 0.0},
        expected_return=0.25,
        expected_risk=0.80,
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = _run_risk_check(result)
    passed = not r["approved"]

    return TestResult(
        name="Extreme Risk (σ = 80%)",
        passed=passed,
        detail=f"Blocked" if passed else "LEAKED THROUGH",
    )


def attack_zero_return() -> TestResult:
    """Attack 3: Zero expected return (should BLOCK)."""
    print("Attack Test 3: Zero Return")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 1, "BTC": 1, "SOL": 0, "AVAX": 0},
        energy=0.0,
        weights={"SUI": 0.33, "ETH": 0.33, "BTC": 0.34, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.0,
        expected_risk=0.15,
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = _run_risk_check(result)
    passed = not r["approved"]

    return TestResult(
        name="Zero Return (E(r) = 0%)",
        passed=passed,
        detail=f"Blocked" if passed else "LEAKED THROUGH",
    )


def attack_slow_solver() -> TestResult:
    """Attack 4: Solver timeout (>5s, should BLOCK)."""
    print("Attack Test 4: Slow Solver (12 seconds)")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 0, "BTC": 1, "SOL": 1, "AVAX": 0},
        energy=-0.5,
        weights={"SUI": 0.33, "ETH": 0.0, "BTC": 0.33, "SOL": 0.34, "AVAX": 0.0},
        expected_return=0.20,
        expected_risk=0.20,
        solver_time_s=12.0,
        solver_used="SlowAttacker",
        feasible=True,
    )

    r = _run_risk_check(result)
    passed = not r["approved"]

    return TestResult(
        name="Slow Solver (>5s timeout)",
        passed=passed,
        detail=f"Blocked" if passed else "LEAKED THROUGH",
    )


def attack_empty_portfolio() -> TestResult:
    """Attack 5: No assets selected (should BLOCK)."""
    print("Attack Test 5: Empty Portfolio")

    result = OptimizationResult(
        allocation={"SUI": 0, "ETH": 0, "BTC": 0, "SOL": 0, "AVAX": 0},
        energy=0.0,
        weights={"SUI": 0.0, "ETH": 0.0, "BTC": 0.0, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.0,
        expected_risk=0.0,
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = _run_risk_check(result)
    passed = not r["approved"]

    return TestResult(
        name="Empty Portfolio (no assets)",
        passed=passed,
        detail=f"Blocked" if passed else "LEAKED THROUGH",
    )


def legit_trade() -> TestResult:
    """Control: Legitimate trade (should PASS)."""
    print("Control: Legitimate Trade")

    try:
        state = run_pipeline(user_id="test-user", risk_tolerance=0.5)
        passed = state.risk_approved

        return TestResult(
            name="Legitimate Trade",
            passed=passed,
            detail=f"Approved" if passed else "REJECTED",
        )
    except Exception as e:
        return TestResult(
            name="Legitimate Trade",
            passed=False,
            detail="Error during execution",
            error=str(e)[:100],
        )


# ===== Main =====

def run_all_tests():
    """Run all safety tests."""
    print("\n" + "="*70)
    print("   COMPREHENSIVE SAFETY TEST SUITE")
    print("="*70)
    print(f"Network:   {NETWORK}")
    print(f"Package:   {PACKAGE_ID}")
    print(f"Portfolio: {PORTFOLIO_ID}")
    print("="*70 + "\n")

    results = []

    # Kill-Switch Tests
    print("KILL-SWITCH TESTS")
    print("-" * 70)
    results.append(kill_switch_test_safe_trade())
    results.append(kill_switch_test_fat_finger())
    results.append(kill_switch_test_cooldown())

    # Redline Tests
    print("\nREDLINE TESTS (Guardrail Verification)")
    print("-" * 70)
    results.append(redline_test_drawdown())
    results.append(redline_test_slippage())
    results.append(redline_test_insufficient_balance())
    results.append(redline_test_100percent_drain())

    # Attack Demo Tests
    print("\nATTACK DEMO TESTS (Risk Agent Validation)")
    print("-" * 70)
    results.append(attack_concentrated_position())
    results.append(attack_extreme_risk())
    results.append(attack_zero_return())
    results.append(attack_slow_solver())
    results.append(attack_empty_portfolio())
    results.append(legit_trade())

    # Summary
    print("\n" + "="*70)
    print("  SUMMARY")
    print("="*70)

    for r in results:
        _print_result(r)

    passed = sum(1 for r in results if r.passed)
    total = len(results)

    print(f"\nTotal: {passed}/{total} passed")

    if passed == total:
        print("\nALL GUARDRAILS HOLDING — SAFE FOR LIVE DEMO")
    else:
        print("\nSOME TESTS FAILED — REVIEW GUARDRAIL CONFIG")

    print("="*70 + "\n")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
