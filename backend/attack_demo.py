#!/usr/bin/env python3
"""
Attack Script — Demonstrates Guardrail Protection.

Simulates malicious/buggy trades that SHOULD be blocked:
  1. Concentrated position (>40% in one asset)
  2. Extreme risk portfolio
  3. Zero-return portfolio
  4. Unauthorized agent address (on-chain only)

Usage:
    python attack_demo.py

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import logging
import sys
import numpy as np

from qubo_optimizer import Asset, OptimizationResult, PortfolioQUBO, QUBOConfig
from agents import (
    risk_agent,
    state_to_dict,
    dict_to_state,
    PipelineState,
)

logging.basicConfig(level=logging.WARNING)


def banner(title: str):
    print(f"\n{'='*60}")
    print(f"  ATTACK #{banner.counter}: {title}")
    print(f"{'='*60}")
    banner.counter += 1
banner.counter = 1


def run_risk_check(opt_result: OptimizationResult) -> dict:
    """Push a fake optimization result through the RiskAgent."""
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


def attack_concentrated_position():
    """Try to put 100% into a single asset."""
    banner("Concentrated Position — 100% SUI")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 0, "BTC": 0, "SOL": 0, "AVAX": 0},
        energy=-1.0,
        weights={"SUI": 1.0, "ETH": 0.0, "BTC": 0.0, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.35,
        expected_risk=0.40,  # σ = 40%
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = run_risk_check(result)
    print(f"  Allocation : 100% SUI")
    print(f"  Status     : {r['status']}")
    print(f"  Blocked?   : {'✅ YES — BLOCKED' if not r['approved'] else '❌ NO — LEAKED THROUGH!'}")
    print(f"  Failed     : {[k for k,v in r['checks'].items() if not v]}")
    for log in r["logs"]:
        print(f"    {log}")
    return not r["approved"]


def attack_extreme_risk():
    """Portfolio with extremely high risk (σ > 35%)."""
    banner("Extreme Risk — σ = 80%")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 1, "BTC": 0, "SOL": 1, "AVAX": 0},
        energy=-2.0,
        weights={"SUI": 0.33, "ETH": 0.33, "BTC": 0.0, "SOL": 0.34, "AVAX": 0.0},
        expected_return=0.25,
        expected_risk=0.80,  # way over 35% cap
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = run_risk_check(result)
    print(f"  Risk (σ)   : 80%")
    print(f"  Status     : {r['status']}")
    print(f"  Blocked?   : {'✅ YES — BLOCKED' if not r['approved'] else '❌ NO — LEAKED THROUGH!'}")
    print(f"  Failed     : {[k for k,v in r['checks'].items() if not v]}")
    for log in r["logs"]:
        print(f"    {log}")
    return not r["approved"]


def attack_zero_return():
    """Portfolio with no expected return."""
    banner("Zero Return — E(r) = 0%")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 1, "BTC": 1, "SOL": 0, "AVAX": 0},
        energy=0.0,
        weights={"SUI": 0.33, "ETH": 0.33, "BTC": 0.34, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.0,   # zero return
        expected_risk=0.15,
        solver_time_s=0.01,
        solver_used="FakeAttacker",
        feasible=True,
    )

    r = run_risk_check(result)
    print(f"  E(r)       : 0%")
    print(f"  Status     : {r['status']}")
    print(f"  Blocked?   : {'✅ YES — BLOCKED' if not r['approved'] else '❌ NO — LEAKED THROUGH!'}")
    print(f"  Failed     : {[k for k,v in r['checks'].items() if not v]}")
    for log in r["logs"]:
        print(f"    {log}")
    return not r["approved"]


def attack_slow_solver():
    """Fake a solver that took too long (>5s)."""
    banner("Slow Solver — 12 seconds")

    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 0, "BTC": 1, "SOL": 1, "AVAX": 0},
        energy=-0.5,
        weights={"SUI": 0.33, "ETH": 0.0, "BTC": 0.33, "SOL": 0.34, "AVAX": 0.0},
        expected_return=0.20,
        expected_risk=0.20,
        solver_time_s=12.0,  # way over 5s budget
        solver_used="SlowAttacker",
        feasible=True,
    )

    r = run_risk_check(result)
    print(f"  Solver time: 12s")
    print(f"  Status     : {r['status']}")
    print(f"  Blocked?   : {'✅ YES — BLOCKED' if not r['approved'] else '❌ NO — LEAKED THROUGH!'}")
    print(f"  Failed     : {[k for k,v in r['checks'].items() if not v]}")
    for log in r["logs"]:
        print(f"    {log}")
    return not r["approved"]


def attack_empty_portfolio():
    """No assets selected at all."""
    banner("Empty Portfolio — 0 assets")

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

    r = run_risk_check(result)
    print(f"  Assets     : none selected")
    print(f"  Status     : {r['status']}")
    print(f"  Blocked?   : {'✅ YES — BLOCKED' if not r['approved'] else '❌ NO — LEAKED THROUGH!'}")
    print(f"  Failed     : {[k for k,v in r['checks'].items() if not v]}")
    for log in r["logs"]:
        print(f"    {log}")
    return not r["approved"]


def legit_trade():
    """A legitimate trade that SHOULD pass (uses mock data for consistent demo)."""
    banner("LEGITIMATE TRADE (should PASS)")

    # Force mock data for consistent demo results
    import agents as _agents
    _orig = _agents.HAS_MARKET_DATA
    _agents.HAS_MARKET_DATA = False

    from agents import run_pipeline
    state = run_pipeline(user_id="legit-user", risk_tolerance=0.5)
    opt = state.optimization_result

    _agents.HAS_MARKET_DATA = _orig  # restore

    print(f"  Status     : {state.status}")
    print(f"  Approved?  : {'✅ YES — PASSED' if state.risk_approved else '❌ NO — FALSE REJECTION!'}")
    if opt:
        selected = [s for s, v in opt.allocation.items() if v == 1]
        print(f"  Selected   : {selected}")
        print(f"  E(r)       : {opt.expected_return:.4f}")
        print(f"  Risk (σ)   : {opt.expected_risk:.4f}")
    for log in state.logs:
        print(f"    {log}")
    return state.risk_approved


def main():
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   GUARDRAIL ATTACK DEMO — CashXChain Risk Protection   ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()
    print("Testing 5 attack vectors + 1 legitimate trade …")

    results = []
    results.append(("Concentrated Position", attack_concentrated_position()))
    results.append(("Extreme Risk", attack_extreme_risk()))
    results.append(("Zero Return", attack_zero_return()))
    results.append(("Slow Solver", attack_slow_solver()))
    results.append(("Empty Portfolio", attack_empty_portfolio()))
    results.append(("Legitimate Trade", legit_trade()))

    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    all_good = True
    for name, passed in results:
        if name == "Legitimate Trade":
            icon = "✅" if passed else "❌"
            expect = "should PASS"
        else:
            icon = "✅" if passed else "❌"
            expect = "should BLOCK"
        print(f"  {icon} {name:30s} ({expect})")
        if not passed:
            all_good = False

    if all_good:
        print(f"\n  🎉 ALL GUARDRAILS WORKING CORRECTLY!")
    else:
        print(f"\n  ⚠️  SOME GUARDRAILS FAILED!")
        sys.exit(1)

    print()


if __name__ == "__main__":
    main()
