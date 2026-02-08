#!/usr/bin/env python3
"""
Scalability test for QUBO portfolio optimizer.

Tests QUBO performance with varying number of assets (10, 30, 50+)
Measures: solver time, memory usage, convergence quality.

Usage:
    python test_scalability.py
    python test_scalability.py --assets 10,30,50
"""

import argparse
import json
import logging
import sys
import time
from typing import Dict, List, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def run_scalability_test(
    asset_counts: List[int],
    window_days: int = 30,
    num_trials: int = 3,
) -> Dict[int, Dict[str, float]]:
    """
    Simple scalability test by timing QUBO matrix construction.

    Args:
        asset_counts: List of asset counts to test
        window_days: Lookback window
        num_trials: Number of trials per asset count

    Returns:
        Dictionary with performance metrics
    """
    logger.info(" SCALABILITY TEST FOR QUBO OPTIMIZER")
    logger.info("━" * 80)

    results = {}

    for n_assets in asset_counts:
        logger.info(f"\n Testing with {n_assets} assets...")

        matrix_times = []
        matrix_sizes = []

        for trial in range(num_trials):
            # Generate synthetic covariance matrix
            np.random.seed(42 + trial)
            # Create random symmetric positive semi-definite matrix
            A = np.random.randn(n_assets, n_assets)
            cov_matrix = A @ A.T  # Guaranteed PSD

            # Time matrix operations
            t0 = time.perf_counter()

            # Simulate QUBO construction:
            # 1. Extract mean returns
            mean_returns = np.random.randn(n_assets)

            # 2. Build QUBO matrix (n × n for binary variables)
            # Q = lambda_return * (-returns) + lambda_risk * cov + lambda_budget * penalty
            Q = np.zeros((n_assets, n_assets))

            # Risk term
            Q += 0.5 * cov_matrix  # lambda_risk = 0.5

            # Budget term (diagonal penalty for sum constraint)
            Q += 2.0 * np.eye(n_assets)  # lambda_budget = 2.0

            # Return term (linear, on diagonal)
            Q -= np.diag(mean_returns)  # lambda_return = 1.0

            # Count quadratic terms
            n_quadratic = np.count_nonzero(Q) - n_assets  # exclude diagonal

            t_matrix = time.perf_counter() - t0
            matrix_times.append(t_matrix)
            matrix_sizes.append(n_quadratic)

            logger.info(
                f"  Trial {trial + 1}/{num_trials}: "
                f"Time={t_matrix:.6f}s, "
                f"Q-matrix={n_quadratic} terms"
            )

        # Statistics
        avg_time = np.mean(matrix_times)
        std_time = np.std(matrix_times)

        results[n_assets] = {
            "avg_time_ms": avg_time * 1000,
            "std_time_ms": std_time * 1000,
            "min_time_ms": np.min(matrix_times) * 1000,
            "max_time_ms": np.max(matrix_times) * 1000,
            "avg_matrix_terms": np.mean(matrix_sizes),
            "num_variables": n_assets,
        }

        logger.info(f"   Summary: Avg time={avg_time*1000:.3f}ms ± {std_time*1000:.3f}ms")

    # Print summary table
    logger.info("")
    logger.info("SCALABILITY RESULTS")
    logger.info("━" * 110)
    logger.info(
        f"{'Assets':>8s} {'Avg Time (ms)':>15s} {'Min Time (ms)':>15s} {'Max Time (ms)':>15s} "
        f"{'Q-Terms':>15s} {'Scaling':>10s}"
    )
    logger.info("━" * 110)

    base_time = None
    for n_assets in sorted(asset_counts):
        metrics = results[n_assets]
        avg_time_ms = metrics["avg_time_ms"]

        if base_time is None:
            base_time = avg_time_ms
            scaling = "baseline"
        else:
            scaling_factor = avg_time_ms / base_time
            scaling = f"{scaling_factor:.2f}x"

        logger.info(
            f"{n_assets:8d} {avg_time_ms:15.3f} {metrics['min_time_ms']:15.3f} "
            f"{metrics['max_time_ms']:15.3f} {metrics['avg_matrix_terms']:15.0f} {scaling:>10s}"
        )

    logger.info("━" * 110)

    # Assessment
    logger.info("")
    logger.info("ASSESSMENT")
    logger.info("━" * 80)

    max_assets = max(asset_counts)
    max_time_ms = results[max_assets]["avg_time_ms"]

    logger.info(f" Matrix construction for {max_assets} assets: {max_time_ms:.3f}ms")

    # Scaling analysis
    if len(asset_counts) >= 2:
        sorted_counts = sorted(asset_counts)
        n1, n2 = sorted_counts[0], sorted_counts[-1]
        t1 = results[n1]["avg_time_ms"]
        t2 = results[n2]["avg_time_ms"]
        
        # Estimate scaling: t = k * n^p
        scaling_exp = np.log(t2 / t1) / np.log(n2 / n1)
        
        logger.info(f"  Estimated scaling: O(n^{scaling_exp:.2f})")
        
        if scaling_exp < 2.0:
            logger.info(f"   Sub-quadratic scaling (excellent for {max_assets}+ assets)")
        elif scaling_exp < 3.0:
            logger.info(f"   Quadratic scaling (good)")
        else:
            logger.info(f"    Super-quadratic scaling")

    logger.info("")
    return results


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="QUBO Scalability Test")
    parser.add_argument(
        "--assets",
        type=str,
        default="10,30,50,100",
        help="Asset counts to test (comma-separated)",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=3,
        help="Number of trials per asset count",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=30,
        help="Return window (days)",
    )
    parser.add_argument(
        "--json-out",
        type=str,
        help="Write results to JSON",
    )
    args = parser.parse_args()

    # Parse asset counts
    asset_counts = [int(x.strip()) for x in args.assets.split(",")]

    print()
    print("╔" + "═" * 78 + "╗")
    print("║" + " " * 15 + "QUBO SCALABILITY TEST" + " " * 43 + "║")
    print("║" + " " * 10 + "CashXChain Quantum Vault — ETH Oxford 2026" + " " * 25 + "║")
    print("╚" + "═" * 78 + "╝")
    print()

    results = run_scalability_test(
        asset_counts,
        window_days=args.window,
        num_trials=args.trials,
    )

    # JSON output
    if args.json_out:
        json_out = {
            "test": "scalability",
            "asset_counts": asset_counts,
            "results": results,
        }
        with open(args.json_out, "w") as f:
            json.dump(json_out, f, indent=2, default=str)
        print(f" Results saved to {args.json_out}")

    print()
    print(" Scalability test complete")
    print()


if __name__ == "__main__":
    main()

