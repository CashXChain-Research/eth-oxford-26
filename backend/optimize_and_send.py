#!/usr/bin/env python3
"""
End-to-end demo: Optimize & Send

Runs the full pipeline:
  1. Market Agent → mock data
  2. Execution Agent → QUBO solve
  3. Risk Agent → pre-flight checks
  4. If approved → submit to Sui (or dry-run)

Usage:
    python optimize_and_send.py
    python optimize_and_send.py --risk 0.8 --dry-run

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import argparse
import json
import logging
import sys
import time

from agents import run_pipeline, state_to_dict
from sui_client import SuiTransactor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("demo")


def main():
    parser = argparse.ArgumentParser(description="Quantum Portfolio Optimizer → Sui")
    parser.add_argument("--risk", type=float, default=0.5, help="Risk tolerance 0.0-1.0")
    parser.add_argument("--user", type=str, default="valentin")
    parser.add_argument("--dry-run", action="store_true", help="Don't submit to chain")
    parser.add_argument("--json-out", type=str, help="Write result JSON to file")
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   QUANTUM-AI PORTFOLIO OPTIMIZER   —   CashXChain   ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    # ---- Step 1-3: Agent Pipeline ----
    t_total = time.perf_counter()
    state = run_pipeline(user_id=args.user, risk_tolerance=args.risk)

    print("\n── Agent Logs ─────────────────────────────────────────")
    for entry in state.logs:
        print(f"  {entry}")

    if state.status != "approved":
        print(f"\n❌ Pipeline result: {state.status}")
        print(f"   Reason: {state.risk_report}")
        if args.json_out:
            _write_json(args.json_out, state, None)
        sys.exit(1)

    opt = state.optimization_result
    print("\n── Optimization Result ────────────────────────────────")
    print(f"  Solver   : {opt.solver_used} ({opt.solver_time_s:.3f}s)")
    print(f"  E(r)     : {opt.expected_return:.4f}")
    print(f"  Risk (σ) : {opt.expected_risk:.4f}")
    print(f"  Energy   : {opt.energy:.4f}")
    print(f"  Allocation:")
    for sym, w in opt.weights.items():
        flag = "✓" if opt.allocation[sym] else " "
        print(f"    [{flag}] {sym:6s}  {w:6.1%}")

    # ---- Step 4: On-chain Execution ----
    print("\n── On-Chain Execution ─────────────────────────────────")
    transactor = SuiTransactor()

    if args.dry_run:
        tx = transactor._dry_run(opt.allocation, opt.weights, "QUBO optimization")
    else:
        tx = transactor.execute_rebalance(
            allocation=opt.allocation,
            weights=opt.weights,
            expected_return=opt.expected_return,
            expected_risk=opt.expected_risk,
            reason=f"QUBO opt | E(r)={opt.expected_return:.4f} σ={opt.expected_risk:.4f}",
        )

    if tx.success:
        print(f"  ✅ Transaction submitted: {tx.digest}")
        print(f"     Gas used: {tx.gas_used}")
    else:
        print(f"  ❌ Transaction failed: {tx.error}")

    elapsed_total = time.perf_counter() - t_total
    print(f"\n  ⏱  Total time: {elapsed_total:.3f}s")
    assert elapsed_total < 5.0, f"Pipeline exceeded 5s budget ({elapsed_total:.1f}s)!"

    # ---- Output ----
    if args.json_out:
        _write_json(args.json_out, state, tx)

    print("\n✨ Done.\n")


def _write_json(path, state, tx):
    """Write full result to JSON."""
    result = state_to_dict(state)
    if tx:
        result["transaction"] = {
            "success": tx.success,
            "digest": tx.digest,
            "gas_used": tx.gas_used,
            "error": tx.error,
        }
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    logger.info(f"Result written to {path}")


if __name__ == "__main__":
    main()
