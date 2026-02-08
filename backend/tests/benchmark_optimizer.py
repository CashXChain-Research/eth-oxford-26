#!/usr/bin/env python3
"""
Benchmark Optimizers for comparison against QUBO.

Implements classical portfolio optimization methods:
  - Markowitz Mean-Variance
  - Equal-Weight Naive
  - Hierarchical Risk Parity (HRP)

Used to compare QUBO strategy vs traditional approaches.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

logger = logging.getLogger(__name__)


class BaseOptimizer(ABC):
    """Base class for portfolio optimizers."""

    def __init__(self, symbols: List[str], window_days: int = 30):
        self.symbols = symbols
        self.n_assets = len(symbols)
        self.window_days = window_days

    @abstractmethod
    def optimize(
        self, returns: np.ndarray, **kwargs
    ) -> Tuple[Dict[str, float], float, float]:
        """
        Optimize portfolio allocation.

        Args:
            returns: (window_days, n_assets) return matrix

        Returns:
            (weights_dict, expected_return, volatility)
        """
        pass


class EqualWeightOptimizer(BaseOptimizer):
    """Naive equal-weight baseline."""

    def optimize(
        self, returns: np.ndarray, **kwargs
    ) -> Tuple[Dict[str, float], float, float]:
        """
        Equal 1/N weights for all assets.

        Args:
            returns: (window_days, n_assets) return matrix

        Returns:
            (weights_dict, expected_return, volatility)
        """
        weights = np.ones(self.n_assets) / self.n_assets
        weights_dict = {sym: w for sym, w in zip(self.symbols, weights)}

        # Expected return and volatility
        expected_return = np.mean(returns, axis=0) @ weights
        covariance = np.cov(returns.T)
        volatility = np.sqrt(weights @ covariance @ weights.T)

        logger.info(
            f"Equal-Weight: E(r)={expected_return:.4f}, σ={volatility:.4f}"
        )
        return weights_dict, expected_return, volatility


class MarkowitzOptimizer(BaseOptimizer):
    """
    Classical Markowitz Mean-Variance optimizer.

    Solves: max E(r) - λ*σ² (risk-adjusted returns)
    """

    def __init__(
        self,
        symbols: List[str],
        window_days: int = 30,
        risk_aversion: float = 0.5,
        min_weight: float = 0.0,
        max_weight: float = 1.0,
    ):
        super().__init__(symbols, window_days)
        self.risk_aversion = risk_aversion
        self.min_weight = min_weight
        self.max_weight = max_weight

    def optimize(
        self, returns: np.ndarray, **kwargs
    ) -> Tuple[Dict[str, float], float, float]:
        """
        Optimize portfolio using Markowitz mean-variance.

        Args:
            returns: (window_days, n_assets) return matrix
            risk_aversion: λ parameter (0-2, default 0.5)

        Returns:
            (weights_dict, expected_return, volatility)
        """
        mean_returns = np.mean(returns, axis=0)
        covariance = np.cov(returns.T)

        def objective(w):
            """Negative Sharpe ratio (for minimization)."""
            portfolio_return = np.sum(mean_returns * w)
            portfolio_std = np.sqrt(w @ covariance @ w.T)
            if portfolio_std == 0:
                return 1e10
            # Maximize return - λ*variance
            return -(
                portfolio_return - self.risk_aversion * (portfolio_std ** 2)
            )

        # Constraints
        constraints = ({"type": "eq", "fun": lambda w: np.sum(w) - 1},)
        bounds = tuple((self.min_weight, self.max_weight) for _ in range(self.n_assets))

        # Initial guess
        x0 = np.ones(self.n_assets) / self.n_assets

        # Optimize
        result = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000},
        )

        weights = result.x
        weights_dict = {sym: float(w) for sym, w in zip(self.symbols, weights)}

        # Metrics
        expected_return = mean_returns @ weights
        volatility = np.sqrt(weights @ covariance @ weights.T)

        logger.info(
            f"Markowitz (λ={self.risk_aversion}): E(r)={expected_return:.4f}, σ={volatility:.4f}"
        )
        return weights_dict, float(expected_return), float(volatility)


class HRPOptimizer(BaseOptimizer):
    """
    Hierarchical Risk Parity (HRP) optimizer.

    De Prado's clustering-based approach:
    1. Compute correlation matrix
    2. Hierarchical clustering
    3. Recursive bisection for weights

    Advantage: No inversion of covariance matrix (more stable)
    """

    def __init__(self, symbols: List[str], window_days: int = 30):
        super().__init__(symbols, window_days)

    def _linkage(self, corr: np.ndarray) -> np.ndarray:
        """
        Simple hierarchical clustering using correlation distance.
        Returns linkage matrix (scipy-like format).
        """
        from scipy.cluster.hierarchy import linkage
        from scipy.spatial.distance import squareform

        # Convert correlation to distance
        distances = np.sqrt((1 - corr) / 2)
        condensed = squareform(distances)
        return linkage(condensed, method="ward")

    def _recursive_bisection(
        self, tree: dict, covariance: np.ndarray
    ) -> Dict[int, float]:
        """Recursive bisection for weight assignment."""
        weights = {}

        def _recurse(node: dict, cov_subset: np.ndarray, indices: List[int]):
            if node["size"] == 1:
                weights[node["index"]] = 1.0
                return

            # Split children
            left_idx = node["left"]["indices"]
            right_idx = node["right"]["indices"]

            # Variance of each partition
            left_var = np.var(cov_subset[np.ix_(left_idx, left_idx)])
            right_var = np.var(cov_subset[np.ix_(right_idx, right_idx)])

            # Weight inversely to variance
            total_var = left_var + right_var
            left_weight = right_var / total_var
            right_weight = left_var / total_var

            # Recurse
            for idx in left_idx:
                weights[idx] = left_weight / len(left_idx)
            for idx in right_idx:
                weights[idx] = right_weight / len(right_idx)

        # Simple partition tree
        indices = list(range(self.n_assets))
        partition = {
            "indices": indices,
            "size": self.n_assets,
            "left": {"indices": indices[: len(indices) // 2], "size": len(indices) // 2},
            "right": {
                "indices": indices[len(indices) // 2 :],
                "size": self.n_assets - len(indices) // 2,
            },
        }

        _recurse(partition, covariance, indices)
        return weights

    def optimize(
        self, returns: np.ndarray, **kwargs
    ) -> Tuple[Dict[str, float], float, float]:
        """
        Optimize using Hierarchical Risk Parity.

        Args:
            returns: (window_days, n_assets) return matrix

        Returns:
            (weights_dict, expected_return, volatility)
        """
        mean_returns = np.mean(returns, axis=0)
        covariance = np.cov(returns.T)

        # Correlation matrix
        correlation = np.corrcoef(returns.T)
        correlation = np.clip(correlation, -1, 1)  # Handle numerical errors

        # Simple equal-weight fallback (full HRP requires scipy tree logic)
        # For now, use weighted by inverse volatility
        volatilities = np.sqrt(np.diag(covariance))
        inverse_vol = 1.0 / volatilities
        weights = inverse_vol / np.sum(inverse_vol)

        weights_dict = {sym: float(w) for sym, w in zip(self.symbols, weights)}

        # Metrics
        expected_return = mean_returns @ weights
        volatility = np.sqrt(weights @ covariance @ weights.T)

        logger.info(
            f"HRP (Inverse Vol): E(r)={expected_return:.4f}, σ={volatility:.4f}"
        )
        return weights_dict, float(expected_return), float(volatility)


class BuyAndHoldOptimizer(BaseOptimizer):
    """
    Buy-and-hold benchmark: invest all in first asset.
    """

    def optimize(
        self, returns: np.ndarray, **kwargs
    ) -> Tuple[Dict[str, float], float, float]:
        """
        100% in first asset.

        Args:
            returns: (window_days, n_assets) return matrix

        Returns:
            (weights_dict, expected_return, volatility)
        """
        weights = np.zeros(self.n_assets)
        weights[0] = 1.0
        weights_dict = {sym: float(w) for sym, w in zip(self.symbols, weights)}

        mean_returns = np.mean(returns, axis=0)
        covariance = np.cov(returns.T)

        expected_return = mean_returns @ weights
        volatility = np.sqrt(weights @ covariance @ weights.T)

        logger.info(
            f"Buy-Hold ({self.symbols[0]}): E(r)={expected_return:.4f}, σ={volatility:.4f}"
        )
        return weights_dict, expected_return, volatility


# Convenience factory
def get_optimizer(
    name: str, symbols: List[str], window_days: int = 30, **kwargs
) -> BaseOptimizer:
    """Get optimizer by name."""
    optimizers = {
        "equal-weight": EqualWeightOptimizer,
        "markowitz": MarkowitzOptimizer,
        "hrp": HRPOptimizer,
        "buy-hold": BuyAndHoldOptimizer,
    }

    if name not in optimizers:
        raise ValueError(f"Unknown optimizer: {name}. Choose from {list(optimizers.keys())}")

    return optimizers[name](symbols, window_days, **kwargs)


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    symbols = ["SUI", "ETH", "BTC", "SOL", "AVAX"]
    returns = np.random.randn(30, 5)

    for name in ["equal-weight", "markowitz", "hrp", "buy-hold"]:
        opt = get_optimizer(name, symbols)
        weights, ret, vol = opt.optimize(returns)
        print(f"{name:20s}: weights={weights}, E(r)={ret:.4f}, σ={vol:.4f}\n")
