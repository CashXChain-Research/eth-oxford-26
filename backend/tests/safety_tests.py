#!/usr/bin/env python3
"""
Safety Tests — Risk agent guardrail validation.

Validates that the RiskAgent correctly blocks:
  - Concentrated positions (100% in one asset)
  - Extreme risk portfolios (σ > 35%)
  - Zero expected return
  - Slow solver (timeout > 5s)
  - Empty portfolios (no assets)
  - And approves legitimate trades
"""

import logging
import sys
from dataclasses import dataclass
from typing import Optional

from agents.manager import (
    PipelineState,
    dict_to_state,
    risk_agent,
    run_pipeline,
    state_to_dict,
)
from quantum.optimizer import OptimizationResult

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(message)s")


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: Optional[str] = None
    error: Optional[str] = None


def _print_result(r: TestResult):
    icon = "PASS" if r.passed else "FAIL"
    print(f"  [{icon}] {r.name}")
    if r.detail:
        print(f"       {r.detail}")
    if r.error and not r.passed:
        print(f"       Error: {r.error[:100]}")
    print()


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
    }


def attack_concentrated_position() -> TestResult:
    """100% in single asset (should BLOCK)."""
    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 0, "BTC": 0, "SOL": 0, "AVAX": 0},
        energy=-1.0,
        weights={"SUI": 1.0, "ETH": 0.0, "BTC": 0.0, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.35, expected_risk=0.40,
        solver_time_s=0.01, solver_used="FakeAttacker", feasible=True,
    )
    r = _run_risk_check(result)
    return TestResult(
        name="Concentrated Position (100% SUI)",
        passed=not r["approved"],
        detail="Blocked" if not r["approved"] else "LEAKED THROUGH",
    )


def attack_extreme_risk() -> TestResult:
    """Extreme risk σ=80% (should BLOCK)."""
    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 1, "BTC": 0, "SOL": 1, "AVAX": 0},
        energy=-2.0,
        weights={"SUI": 0.33, "ETH": 0.33, "BTC": 0.0, "SOL": 0.34, "AVAX": 0.0},
        expected_return=0.25, expected_risk=0.80,
        solver_time_s=0.01, solver_used="FakeAttacker", feasible=True,
    )
    r = _run_risk_check(result)
    return TestResult(
        name="Extreme Risk (σ = 80%)",
        passed=not r["approved"],
        detail="Blocked" if not r["approved"] else "LEAKED THROUGH",
    )


def attack_zero_return() -> TestResult:
    """Zero expected return (should BLOCK)."""
    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 1, "BTC": 1, "SOL": 0, "AVAX": 0},
        energy=0.0,
        weights={"SUI": 0.33, "ETH": 0.33, "BTC": 0.34, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.0, expected_risk=0.15,
        solver_time_s=0.01, solver_used="FakeAttacker", feasible=True,
    )
    r = _run_risk_check(result)
    return TestResult(
        name="Zero Return (E(r) = 0%)",
        passed=not r["approved"],
        detail="Blocked" if not r["approved"] else "LEAKED THROUGH",
    )


def attack_slow_solver() -> TestResult:
    """Solver timeout >5s (should BLOCK)."""
    result = OptimizationResult(
        allocation={"SUI": 1, "ETH": 0, "BTC": 1, "SOL": 1, "AVAX": 0},
        energy=-0.5,
        weights={"SUI": 0.33, "ETH": 0.0, "BTC": 0.33, "SOL": 0.34, "AVAX": 0.0},
        expected_return=0.20, expected_risk=0.20,
        solver_time_s=12.0, solver_used="SlowAttacker", feasible=True,
    )
    r = _run_risk_check(result)
    return TestResult(
        name="Slow Solver (>5s timeout)",
        passed=not r["approved"],
        detail="Blocked" if not r["approved"] else "LEAKED THROUGH",
    )


def attack_empty_portfolio() -> TestResult:
    """No assets selected (should BLOCK)."""
    result = OptimizationResult(
        allocation={"SUI": 0, "ETH": 0, "BTC": 0, "SOL": 0, "AVAX": 0},
        energy=0.0,
        weights={"SUI": 0.0, "ETH": 0.0, "BTC": 0.0, "SOL": 0.0, "AVAX": 0.0},
        expected_return=0.0, expected_risk=0.0,
        solver_time_s=0.01, solver_used="FakeAttacker", feasible=True,
    )
    r = _run_risk_check(result)
    return TestResult(
        name="Empty Portfolio (no assets)",
        passed=not r["approved"],
        detail="Blocked" if not r["approved"] else "LEAKED THROUGH",
    )


def legit_trade() -> TestResult:
    """Control: Legitimate trade (should PASS)."""
    try:
        state = run_pipeline(user_id="test-user", risk_tolerance=0.5)
        return TestResult(
            name="Legitimate Trade",
            passed=state.risk_approved,
            detail="Approved" if state.risk_approved else "REJECTED",
        )
    except Exception as e:
        return TestResult(
            name="Legitimate Trade", passed=False,
            detail="Error during execution", error=str(e)[:100],
        )


def run_all_tests():
    """Run all safety tests."""
    print("\n" + "=" * 60)
    print("  SAFETY TESTS — Risk Agent Guardrails")
    print("=" * 60 + "\n")

    results = [
        attack_concentrated_position(),
        attack_extreme_risk(),
        attack_zero_return(),
        attack_slow_solver(),
        attack_empty_portfolio(),
        legit_trade(),
    ]

    print("\n" + "=" * 60)
    for r in results:
        _print_result(r)

    passed = sum(1 for r in results if r.passed)
    print(f"Total: {passed}/{len(results)} passed\n")
    return passed == len(results)


if __name__ == "__main__":
    sys.exit(0 if run_all_tests() else 1)
