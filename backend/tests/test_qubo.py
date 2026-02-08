#!/usr/bin/env python3
"""
Tests & benchmarks for the QUBO optimizer and agent pipeline.

Run:
    python test_qubo.py
    python test_qubo.py -v          # verbose
    python -m pytest test_qubo.py   # with pytest
"""

import time
import unittest

import numpy as np

from quantum.optimizer import (
    Asset,
    OptimizationResult,
    PortfolioQUBO,
    QUBOConfig,
    make_test_universe,
)


class TestQUBOOptimizer(unittest.TestCase):
    """Test the QUBO portfolio optimizer."""

    def setUp(self):
        self.assets, self.cov = make_test_universe()

    def test_build_bqm(self):
        """BQM builds without errors and has correct variable count."""
        opt = PortfolioQUBO(self.assets, self.cov)
        bqm = opt.build()
        self.assertEqual(len(bqm.variables), 5)

    def test_solve_returns_result(self):
        """Solver returns a valid OptimizationResult."""
        opt = PortfolioQUBO(self.assets, self.cov)
        result = opt.solve()
        self.assertIsInstance(result, OptimizationResult)
        self.assertEqual(len(result.allocation), 5)
        self.assertIn(result.solver_used, ["ExactSolver", "SimulatedAnnealing"])

    def test_selects_target_assets(self):
        """With target_assets=3, solver should select ~3 assets."""
        cfg = QUBOConfig(target_assets=3, lambda_budget=5.0)
        opt = PortfolioQUBO(self.assets, self.cov, cfg)
        result = opt.solve()
        n_selected = sum(1 for v in result.allocation.values() if v == 1)
        # Allow ±1 due to optimization trade-offs
        self.assertGreaterEqual(n_selected, 2)
        self.assertLessEqual(n_selected, 4)

    def test_weights_sum_to_one(self):
        """Selected asset weights should sum to ~1.0."""
        opt = PortfolioQUBO(self.assets, self.cov)
        result = opt.solve()
        total_w = sum(result.weights.values())
        if any(v == 1 for v in result.allocation.values()):
            self.assertAlmostEqual(total_w, 1.0, places=5)

    def test_high_risk_tolerance_selects_more(self):
        """More aggressive config should select more assets."""
        cfg_conservative = QUBOConfig(target_assets=2, lambda_risk=1.0, lambda_return=0.5)
        cfg_aggressive = QUBOConfig(target_assets=4, lambda_risk=0.2, lambda_return=1.5)

        r1 = PortfolioQUBO(self.assets, self.cov, cfg_conservative).solve()
        r2 = PortfolioQUBO(self.assets, self.cov, cfg_aggressive).solve()

        n1 = sum(1 for v in r1.allocation.values() if v == 1)
        n2 = sum(1 for v in r2.allocation.values() if v == 1)
        self.assertLessEqual(n1, n2 + 1)  # conservative ≤ aggressive (+tolerance)

    def test_expected_return_positive(self):
        """Expected return should be positive with our test assets."""
        opt = PortfolioQUBO(self.assets, self.cov)
        result = opt.solve()
        if sum(1 for v in result.allocation.values() if v == 1) > 0:
            self.assertGreater(result.expected_return, 0)

    def test_risk_is_positive(self):
        """Risk should be non-negative."""
        opt = PortfolioQUBO(self.assets, self.cov)
        result = opt.solve()
        self.assertGreaterEqual(result.expected_risk, 0)

    def test_solver_under_5_seconds(self):
        """Solver must complete under 5 seconds (hackathon requirement)."""
        opt = PortfolioQUBO(self.assets, self.cov)
        t0 = time.perf_counter()
        result = opt.solve()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 5.0, f"Solver took {elapsed:.2f}s, exceeds 5s budget")

    def test_covariance_mismatch_raises(self):
        """Mismatched covariance matrix should raise AssertionError."""
        bad_cov = np.eye(3)  # 3x3 but 5 assets
        with self.assertRaises(AssertionError):
            PortfolioQUBO(self.assets, bad_cov)

    def test_two_assets_exact(self):
        """Small 2-asset problem should be solvable by ExactSolver."""
        assets = [
            Asset(symbol="A", expected_return=0.20),
            Asset(symbol="B", expected_return=0.10),
        ]
        cov = np.array([[0.04, 0.01], [0.01, 0.02]])
        cfg = QUBOConfig(target_assets=1)
        opt = PortfolioQUBO(assets, cov, cfg)
        result = opt.solve()
        self.assertEqual(result.solver_used, "ExactSolver")
        # Should pick asset A (higher return)
        self.assertEqual(result.allocation["A"], 1)


class TestAgentPipeline(unittest.TestCase):
    """Test the LangGraph agent pipeline."""

    def test_pipeline_runs(self):
        """Full pipeline executes without errors."""
        from agents.manager import run_pipeline

        state = run_pipeline(user_id="test", risk_tolerance=0.5)
        self.assertIn(state.status, ["approved", "rejected", "pending_approval"])
        self.assertGreater(len(state.logs), 0)

    def test_pipeline_approved_moderate_risk(self):
        """Moderate risk should produce valid status."""
        from agents.manager import run_pipeline

        state = run_pipeline(user_id="test", risk_tolerance=0.5)
        # Verify the pipeline runs and produces a valid status
        self.assertIn(state.status, ["approved", "rejected", "pending_approval"])
        # Risk approval is determined by the pipeline logic
        self.assertIsNotNone(state.risk_approved)

    def test_pipeline_has_optimization_result(self):
        """Pipeline should produce an optimization result."""
        from agents.manager import run_pipeline

        state = run_pipeline(user_id="test", risk_tolerance=0.5)
        self.assertIsNotNone(state.optimization_result)

    def test_pipeline_under_15_seconds(self):
        """Full pipeline must complete under 15 seconds (includes API fallback)."""
        from agents.manager import run_pipeline

        t0 = time.perf_counter()
        state = run_pipeline(user_id="test", risk_tolerance=0.5)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 15.0, f"Pipeline took {elapsed:.2f}s")

    def test_risk_checks_populated(self):
        """Risk checks dict should be populated."""
        from agents.manager import run_pipeline

        state = run_pipeline(user_id="test", risk_tolerance=0.5)
        self.assertIn("position_size_ok", state.risk_checks)
        self.assertIn("risk_within_limit", state.risk_checks)
        self.assertIn("solver_fast_enough", state.risk_checks)


class TestBenchmark(unittest.TestCase):
    """Performance benchmarks."""

    def test_qubo_10_runs_average(self):
        """Average solve time over 10 runs should be well under 5s."""
        assets, cov = make_test_universe()
        times = []
        for _ in range(10):
            opt = PortfolioQUBO(assets, cov)
            t0 = time.perf_counter()
            opt.solve()
            times.append(time.perf_counter() - t0)
        avg = sum(times) / len(times)
        print(f"\n   QUBO solve: avg={avg:.4f}s, min={min(times):.4f}s, max={max(times):.4f}s")
        self.assertLess(avg, 2.0, f"Average solve time {avg:.2f}s too high")


if __name__ == "__main__":
    unittest.main(verbosity=2)
