#!/usr/bin/env python3
"""
Portfolio Optimization via QUBO (Quadratic Unconstrained Binary Optimization).

Formulation:
    E(x) = x^T Q x + c^T x

Where:
    - x ∈ {0,1}^n  — binary vector: 1 = allocate to asset i
    - Q  = λ_risk * Σ  (covariance matrix, encodes risk)
    - c  = -λ_return * μ + λ_budget * penalty_terms  (linear bias)
    - Σ  = covariance matrix of asset returns
    - μ  = expected return vector

Supports:
    - D-Wave Ocean SDK (real QPU or SimulatedAnnealingSampler)
    - Neal (simulated annealing, no cloud needed)
    - Exact solver for tiny problems (≤20 vars)

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import dimod
    from neal import SimulatedAnnealingSampler
except ImportError:
    raise ImportError("Install D-Wave Ocean SDK: pip install dimod dwave-neal")

try:
    from dwave.system import DWaveSampler, EmbeddingComposite

    HAS_DWAVE_QPU = True
except ImportError:
    HAS_DWAVE_QPU = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Asset:
    """Single tradeable asset."""

    symbol: str
    expected_return: float  # annualized μ
    current_weight: float = 0.0  # current portfolio weight [0,1]
    max_weight: float = 0.40  # guardrail: max position size


@dataclass
class OptimizationResult:
    """Result of a QUBO portfolio optimization run."""

    allocation: Dict[str, int]  # symbol → 0/1
    energy: float  # objective value
    weights: Dict[str, float]  # symbol → normalized weight
    expected_return: float
    expected_risk: float
    solver_time_s: float
    solver_used: str
    feasible: bool = True
    reason: str = ""


@dataclass
class QUBOConfig:
    """Hyperparameters for QUBO formulation."""

    lambda_return: float = 1.0  # weight on returns
    lambda_risk: float = 0.5  # weight on risk (covariance)
    lambda_budget: float = 2.0  # penalty for budget constraint
    target_assets: int = 3  # how many assets to pick (budget)
    num_reads: int = 200  # SA / QPU samples
    use_qpu: bool = False  # use real D-Wave QPU


# ---------------------------------------------------------------------------
# QUBO Builder
# ---------------------------------------------------------------------------


class PortfolioQUBO:
    """Build and solve the portfolio optimization QUBO."""

    def __init__(
        self,
        assets: List[Asset],
        cov_matrix: np.ndarray,
        config: Optional[QUBOConfig] = None,
    ):
        self.assets = assets
        self.n = len(assets)
        self.cov = cov_matrix  # (n, n)
        self.cfg = config or QUBOConfig()

        assert cov_matrix.shape == (
            self.n,
            self.n,
        ), f"Covariance matrix shape mismatch: {cov_matrix.shape} vs ({self.n},{self.n})"

        self._bqm: Optional[dimod.BinaryQuadraticModel] = None

    # ----- continuous weight optimization (post-QUBO) -----

    def _optimize_continuous_weights(
        self,
        selected_indices: List[int],
    ) -> tuple:
        """
        After binary asset selection via QUBO, compute optimal continuous
        weights using mean-variance optimization on the selected sub-universe.

        Solves:  min  w^T Σ_sel w  -  λ * μ_sel^T w
                 s.t. Σ w_i = 1,  min_w ≤ w_i ≤ max_weight_i

        Uses iterative quadratic solver (analytical + projection).
        Falls back to equal-weight if optimization is infeasible.

        Returns: (weights_dict, expected_return, expected_risk)
        """
        n_sel = len(selected_indices)
        MIN_WEIGHT = 0.05  # every QUBO-selected asset gets at least 5%

        sub_mu = np.array([self.assets[i].expected_return for i in selected_indices])
        sub_cov = self.cov[np.ix_(selected_indices, selected_indices)]
        max_weights = np.array([self.assets[i].max_weight for i in selected_indices])

        # Risk-return trade-off parameter (from config)
        lam = self.cfg.lambda_risk / max(self.cfg.lambda_return, 1e-8)

        # ---- Analytical unconstrained solution ----
        # w* ∝ Σ^{-1} μ  (tangency portfolio direction)
        try:
            inv_cov = np.linalg.inv(sub_cov)
            raw_w = inv_cov @ sub_mu
            # If all weights are negative (extreme risk aversion), use min-variance
            if np.all(raw_w <= 0):
                ones = np.ones(n_sel)
                raw_w = inv_cov @ ones
        except np.linalg.LinAlgError:
            # Singular covariance — fall back to equal weight
            raw_w = np.ones(n_sel)

        # ---- Normalize to sum=1, enforce bounds via projection ----
        w = self._project_simplex_bounded(raw_w, max_weights, n_iters=50)

        # ---- Ensure QUBO-selected assets get meaningful allocation ----
        # The tangency portfolio (Σ⁻¹μ) can be very concentrated when
        # assets are correlated, assigning 0% to some selected assets.
        # Since the QUBO already decided these assets should be in the
        # portfolio, enforce a minimum weight and re-project.
        if n_sel > 1 and np.any(w < MIN_WEIGHT):
            # Blend with equal-weight to ensure diversification
            equal_w = np.ones(n_sel) / n_sel
            blended = 0.5 * w + 0.5 * equal_w
            w = self._project_simplex_bounded(blended, max_weights, n_iters=50)
            # Final enforcement: floor at MIN_WEIGHT, redistribute
            if np.any(w < MIN_WEIGHT):
                w = np.maximum(w, MIN_WEIGHT)
                excess = w.sum() - 1.0
                if excess > 0:
                    # Remove excess from largest weights
                    for _ in range(20):
                        idx_max = np.argmax(w)
                        reduce = min(excess, w[idx_max] - MIN_WEIGHT)
                        w[idx_max] -= reduce
                        excess -= reduce
                        if abs(excess) < 1e-10:
                            break
                w = w / w.sum()  # safety re-normalize

        # ---- Compute portfolio metrics ----
        exp_ret = float(w @ sub_mu)
        exp_risk = float(np.sqrt(w @ sub_cov @ w))

        # Build full weights dict
        weights = {self.assets[i].symbol: 0.0 for i in range(self.n)}
        for idx_pos, idx_asset in enumerate(selected_indices):
            weights[self.assets[idx_asset].symbol] = float(w[idx_pos])

        logger.info(
            f"Continuous weights: "
            + ", ".join(
                f"{self.assets[i].symbol}={w[j]:.2%}" for j, i in enumerate(selected_indices)
            )
        )

        return weights, exp_ret, exp_risk

    @staticmethod
    def _project_simplex_bounded(
        w: np.ndarray,
        upper_bounds: np.ndarray,
        n_iters: int = 50,
    ) -> np.ndarray:
        """
        Project weights onto the bounded simplex:
            Σ w_i = 1,  0 ≤ w_i ≤ ub_i

        Uses Dykstra's alternating projection between the simplex and
        the box constraints.
        """
        n = len(w)
        # Normalize to sum=1 BEFORE clipping to preserve relative ratios
        w = np.maximum(w, 0.0)
        s = w.sum()
        if s > 1e-12:
            w = w / s
        else:
            w = np.ones(n) / n

        for _ in range(n_iters):
            # Project onto box [0, ub]
            clamped = np.clip(w, 0.0, upper_bounds)
            excess = clamped.sum() - 1.0
            if abs(excess) < 1e-10:
                w = clamped
                break
            # Distribute excess among non-capped variables
            if excess > 0:
                free_mask = clamped < upper_bounds - 1e-10
            else:
                free_mask = clamped > 1e-10
            n_free = free_mask.sum()
            if n_free == 0:
                # All at boundaries — scale proportionally
                s = clamped.sum()
                if s > 1e-12:
                    w = clamped / s
                break
            clamped[free_mask] -= excess / n_free
            w = clamped

        # Final safety
        w = np.clip(w, 0.0, upper_bounds)
        s = w.sum()
        if abs(s - 1.0) > 1e-8 and s > 1e-12:
            w = w / s

        return w

    # ----- build -----

    def build(self) -> dimod.BinaryQuadraticModel:
        """
        Construct the BQM (Binary Quadratic Model).

        E(x) = λ_risk * x^T Σ x
             - λ_return * μ^T x
             + λ_budget * (Σ x_i - K)^2

        The budget penalty expands to:
            λ_budget * [ Σ_i x_i^2  +  2 Σ_{i<j} x_i x_j  -  2K Σ_i x_i  + K^2 ]
        Since x_i ∈ {0,1}, x_i^2 = x_i.
        """
        cfg = self.cfg
        mu = np.array([a.expected_return for a in self.assets])
        K = cfg.target_assets

        # --- Linear biases h_i ---
        h = np.zeros(self.n)
        # Return term: -λ_return * μ_i
        h -= cfg.lambda_return * mu
        # Risk diagonal: λ_risk * Σ_ii  (x_i^2 = x_i for binary)
        h += cfg.lambda_risk * np.diag(self.cov)
        # Budget penalty diagonal: λ_budget * (1 - 2K)  per variable
        h += cfg.lambda_budget * (1.0 - 2.0 * K)

        # --- Quadratic biases J_{ij} ---
        J = {}
        for i in range(self.n):
            for j in range(i + 1, self.n):
                q_ij = 0.0
                # Risk: λ_risk * Σ_ij  (off-diagonal, factor 2 already in upper tri)
                q_ij += cfg.lambda_risk * 2.0 * self.cov[i, j]
                # Budget penalty coupling: 2 * λ_budget
                q_ij += 2.0 * cfg.lambda_budget
                if abs(q_ij) > 1e-12:
                    J[(i, j)] = q_ij

        # Build BQM
        linear = {i: float(h[i]) for i in range(self.n)}
        bqm = dimod.BinaryQuadraticModel(linear, J, 0.0, dimod.BINARY)

        # Offset (constant from budget penalty): λ_budget * K^2
        bqm.offset += cfg.lambda_budget * K * K

        self._bqm = bqm
        logger.info(
            f"Built QUBO: {self.n} variables, " f"{len(J)} quadratic terms, target_assets={K}"
        )
        return bqm

    # ----- solve -----

    def solve(self) -> OptimizationResult:
        """Solve the QUBO and return the best allocation."""
        if self._bqm is None:
            self.build()

        t0 = time.perf_counter()

        if self.cfg.use_qpu and HAS_DWAVE_QPU:
            solver_name = "DWave-QPU"
            sampler = EmbeddingComposite(DWaveSampler())
            response = sampler.sample(
                self._bqm, num_reads=self.cfg.num_reads, label="portfolio-opt"
            )
        elif self.n <= 20:
            # Exact solver for small problems (good for demos)
            solver_name = "ExactSolver"
            sampler = dimod.ExactSolver()
            response = sampler.sample(self._bqm)
        else:
            solver_name = "SimulatedAnnealing"
            sampler = SimulatedAnnealingSampler()
            response = sampler.sample(
                self._bqm,
                num_reads=self.cfg.num_reads,
                num_sweeps=1000,
            )

        elapsed = time.perf_counter() - t0

        # Best sample
        best = response.first
        sample = best.sample
        energy = best.energy

        # Map back to assets
        allocation = {}
        selected_indices = []
        for i in range(self.n):
            val = sample.get(i, 0)
            allocation[self.assets[i].symbol] = int(val)
            if val == 1:
                selected_indices.append(i)

        # Compute portfolio metrics with CONTINUOUS weight optimization
        n_selected = len(selected_indices)
        if n_selected > 0:
            weights, exp_ret, exp_risk = self._optimize_continuous_weights(selected_indices)
        else:
            weights = {a.symbol: 0.0 for a in self.assets}
            exp_ret = 0.0
            exp_risk = 0.0

        # Feasibility check (guardrails)
        feasible = True
        reason = ""
        for i in selected_indices:
            w_i = weights[self.assets[i].symbol]
            if w_i > self.assets[i].max_weight:
                feasible = False
                reason = (
                    f"{self.assets[i].symbol} weight {w_i:.2%} > "
                    f"max {self.assets[i].max_weight:.2%}"
                )
                break

        result = OptimizationResult(
            allocation=allocation,
            energy=energy,
            weights=weights,
            expected_return=exp_ret,
            expected_risk=exp_risk,
            solver_time_s=elapsed,
            solver_used=solver_name,
            feasible=feasible,
            reason=reason,
        )

        logger.info(
            f"Solved in {elapsed:.3f}s ({solver_name}): "
            f"selected={[a for a, v in allocation.items() if v == 1]}, "
            f"E(r)={exp_ret:.4f}, σ={exp_risk:.4f}, energy={energy:.4f}"
        )
        return result


# ---------------------------------------------------------------------------
# Convenience: 5 test-asset universe
# ---------------------------------------------------------------------------


def make_test_universe() -> Tuple[List[Asset], np.ndarray]:
    """
    Return 5 mock crypto assets and a realistic covariance matrix.
    Assets: SUI, ETH, BTC, SOL, AVAX
    """
    assets = [
        Asset(symbol="SUI", expected_return=0.35, max_weight=0.40),
        Asset(symbol="ETH", expected_return=0.20, max_weight=0.40),
        Asset(symbol="BTC", expected_return=0.15, max_weight=0.40),
        Asset(symbol="SOL", expected_return=0.30, max_weight=0.40),
        Asset(symbol="AVAX", expected_return=0.25, max_weight=0.40),
    ]
    # Covariance matrix (annualized, synthetic but realistic correlations)
    cov = np.array(
        [
            [0.160, 0.048, 0.030, 0.070, 0.055],  # SUI
            [0.048, 0.090, 0.045, 0.040, 0.035],  # ETH
            [0.030, 0.045, 0.050, 0.025, 0.020],  # BTC
            [0.070, 0.040, 0.025, 0.140, 0.060],  # SOL
            [0.055, 0.035, 0.020, 0.060, 0.110],  # AVAX
        ]
    )
    return assets, cov


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------


def main():
    import argparse
    import json as _json

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="QUBO Portfolio Optimizer")
    parser.add_argument("--target", type=int, default=3, help="Number of assets to select")
    parser.add_argument("--risk-weight", type=float, default=0.5)
    parser.add_argument("--return-weight", type=float, default=1.0)
    parser.add_argument("--qpu", action="store_true", help="Use real D-Wave QPU")
    args = parser.parse_args()

    assets, cov = make_test_universe()
    cfg = QUBOConfig(
        lambda_return=args.return_weight,
        lambda_risk=args.risk_weight,
        target_assets=args.target,
        use_qpu=args.qpu,
    )
    optimizer = PortfolioQUBO(assets, cov, cfg)
    result = optimizer.solve()

    print("\n" + "=" * 50)
    print("QUBO PORTFOLIO OPTIMIZATION RESULT")
    print("=" * 50)
    print(f"Solver       : {result.solver_used}")
    print(f"Time         : {result.solver_time_s:.3f}s")
    print(f"Energy       : {result.energy:.4f}")
    print(f"Exp. Return  : {result.expected_return:.4f}")
    print(f"Exp. Risk (σ): {result.expected_risk:.4f}")
    print(f"Feasible     : {result.feasible}")
    print(f"Allocation   :")
    for sym, w in result.weights.items():
        flag = "" if result.allocation[sym] else " "
        print(f"  [{flag}] {sym:6s}  {w:6.1%}")

    # JSON for piping
    print(
        "\n"
        + _json.dumps(
            {
                "allocation": result.allocation,
                "weights": result.weights,
                "expected_return": result.expected_return,
                "expected_risk": result.expected_risk,
                "energy": result.energy,
                "solver": result.solver_used,
                "time_s": result.solver_time_s,
                "feasible": result.feasible,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
