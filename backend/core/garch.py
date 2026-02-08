#!/usr/bin/env python3
"""
GARCH(1,1) Volatility Forecasting Module.

Replaces naive historical standard deviation with a proper econometric model:

  σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}

Where:
  - ω (omega) = long-run variance baseline
  - α (alpha) = reaction to recent shocks (ARCH term)
  - β (beta)  = persistence of past volatility (GARCH term)

This captures volatility clustering — the empirical fact that large price
moves tend to be followed by more large moves. Naive std treats all 30 days
equally; GARCH weights recent shocks more heavily.

Uses the `arch` library (Kevin Sheppard, Oxford) for estimation.

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

GARCH_AVAILABLE = False
try:
    from arch import arch_model

    GARCH_AVAILABLE = True
except ImportError:
    logger.warning("arch library not installed — GARCH disabled, falling back to EWMA")


@dataclass
class VolatilityForecast:
    """Result of GARCH volatility forecasting for a single asset."""

    symbol: str
    # Annualized volatility estimates
    historical_vol: float  # naive std (what we had before)
    forecast_vol: float  # GARCH 1-step forecast
    # GARCH model parameters (if fitted)
    omega: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    persistence: float = 0.0  # α + β (should be < 1 for stationarity)
    # Model quality
    log_likelihood: float = 0.0
    model_used: str = "garch"  # "garch" or "ewma_fallback"


def fit_garch(
    returns: np.ndarray,
    symbol: str = "UNKNOWN",
    horizon: int = 1,
) -> VolatilityForecast:
    """
    Fit GARCH(1,1) to a return series and produce a h-step volatility forecast.

    Args:
        returns: Array of daily log returns (at least 20 observations).
        symbol: Asset symbol for logging.
        horizon: Forecast horizon in days (default 1).

    Returns:
        VolatilityForecast with both historical and GARCH-based estimates.
    """
    # Historical (naive) volatility — annualized
    hist_vol = float(np.std(returns, ddof=1) * np.sqrt(365))

    if not GARCH_AVAILABLE or len(returns) < 20:
        logger.debug(f"[{symbol}] GARCH unavailable or too few obs ({len(returns)}), using EWMA")
        ewma_vol = _ewma_volatility(returns)
        return VolatilityForecast(
            symbol=symbol,
            historical_vol=hist_vol,
            forecast_vol=ewma_vol,
            model_used="ewma_fallback",
        )

    try:
        # Scale returns to percentage for numerical stability
        scaled = returns * 100.0

        # Fit GARCH(1,1) with constant mean
        model = arch_model(
            scaled,
            vol="Garch",
            p=1,
            q=1,
            mean="Constant",
            dist="normal",
            rescale=False,
        )
        result = model.fit(disp="off", show_warning=False)

        # Extract parameters
        params = result.params
        omega = float(params.get("omega", 0))
        alpha = float(params.get("alpha[1]", 0))
        beta = float(params.get("beta[1]", 0))
        persistence = alpha + beta

        # h-step ahead variance forecast
        forecasts = result.forecast(horizon=horizon, reindex=False)
        # variance is in (pct²), convert back: divide by 100² then annualize
        forecast_var_pct = float(forecasts.variance.iloc[-1].values[-1])
        daily_var = forecast_var_pct / (100.0 ** 2)
        annual_vol = float(np.sqrt(daily_var * 365))

        logger.info(
            f"[{symbol}] GARCH(1,1): ω={omega:.6f}, α={alpha:.4f}, β={beta:.4f}, "
            f"persistence={persistence:.4f}, σ_forecast={annual_vol:.4f}"
        )

        return VolatilityForecast(
            symbol=symbol,
            historical_vol=hist_vol,
            forecast_vol=annual_vol,
            omega=omega,
            alpha=alpha,
            beta=beta,
            persistence=persistence,
            log_likelihood=float(result.loglikelihood),
            model_used="garch",
        )

    except Exception as e:
        logger.warning(f"[{symbol}] GARCH fit failed ({e}), falling back to EWMA")
        ewma_vol = _ewma_volatility(returns)
        return VolatilityForecast(
            symbol=symbol,
            historical_vol=hist_vol,
            forecast_vol=ewma_vol,
            model_used="ewma_fallback",
        )


def _ewma_volatility(returns: np.ndarray, span: int = 10) -> float:
    """
    Exponentially-Weighted Moving Average volatility (annualized).
    Simpler fallback when GARCH can't fit.
    """
    decay = 2.0 / (span + 1)
    weights = np.array([(1 - decay) ** i for i in range(len(returns) - 1, -1, -1)])
    weights /= weights.sum()
    ewma_var = float(np.sum(weights * (returns - np.mean(returns)) ** 2))
    return float(np.sqrt(ewma_var * 365))


def forecast_covariance_garch(
    return_matrix: np.ndarray,
    symbols: List[str],
) -> Tuple[np.ndarray, List[VolatilityForecast]]:
    """
    Build a GARCH-enhanced covariance matrix.

    Strategy: DCC-lite (Diagonal GARCH)
      1. Fit univariate GARCH(1,1) to each asset → forecasted σ_i
      2. Compute correlation matrix from raw returns (DCC simplified)
      3. Construct Σ = D · R · D where D = diag(σ_forecasts)

    This gives a forward-looking covariance matrix instead of the backward-
    looking np.cov() that treats all observations equally.

    Args:
        return_matrix: (n_assets, n_days) array of daily log returns.
        symbols: List of asset symbols, same order as return_matrix rows.

    Returns:
        (cov_matrix, forecasts) — the GARCH-enhanced cov and per-asset forecasts.
    """
    n_assets = return_matrix.shape[0]
    forecasts: List[VolatilityForecast] = []

    # Step 1: Univariate GARCH for each asset
    daily_vols = np.zeros(n_assets)
    for i in range(n_assets):
        fc = fit_garch(return_matrix[i], symbol=symbols[i])
        forecasts.append(fc)
        # Convert annualized vol back to daily for matrix construction
        daily_vols[i] = fc.forecast_vol / np.sqrt(365)

    # Step 2: Correlation matrix from standardized returns
    # (Using DCC simplification: static correlation from historical data)
    std_returns = np.zeros_like(return_matrix)
    for i in range(n_assets):
        s = np.std(return_matrix[i], ddof=1)
        if s > 0:
            std_returns[i] = return_matrix[i] / s
        else:
            std_returns[i] = return_matrix[i]

    corr = np.corrcoef(std_returns)
    # Clean up numerical noise
    corr = (corr + corr.T) / 2
    np.fill_diagonal(corr, 1.0)

    # Step 3: Σ = D · R · D (annualized)
    D = np.diag(daily_vols)
    cov = D @ corr @ D

    # Annualize
    cov_annual = cov * 365

    # Ensure positive semi-definite
    cov_annual = (cov_annual + cov_annual.T) / 2
    eigvals = np.linalg.eigvalsh(cov_annual)
    if eigvals.min() < 0:
        cov_annual -= 1.1 * eigvals.min() * np.eye(n_assets)

    models_used = {fc.model_used for fc in forecasts}
    logger.info(
        f"GARCH covariance: {n_assets} assets, models={models_used}, "
        f"cond={np.linalg.cond(cov_annual):.1f}"
    )

    return cov_annual, forecasts


# ── CLI test ─────────────────────────────────────────


def main():
    """Quick self-test with synthetic data."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    np.random.seed(42)
    n_days = 60
    symbols = ["SUI", "BTC", "ETH", "SOL", "AVAX"]

    # Generate synthetic returns with volatility clustering
    returns = []
    for i, sym in enumerate(symbols):
        # Simulate GARCH-like process
        vol = 0.02 + i * 0.005  # baseline daily vol
        r = np.zeros(n_days)
        sigma = vol
        for t in range(n_days):
            r[t] = np.random.normal(0.0003, sigma)
            sigma = np.sqrt(0.00001 + 0.1 * r[t] ** 2 + 0.85 * sigma ** 2)
        returns.append(r)

    return_matrix = np.array(returns)

    print("\n── GARCH Volatility Forecasts ──")
    cov, forecasts = forecast_covariance_garch(return_matrix, symbols)

    for fc in forecasts:
        delta = fc.forecast_vol - fc.historical_vol
        direction = "↑" if delta > 0 else "↓"
        print(
            f"  {fc.symbol:6s}  historical={fc.historical_vol:.4f}  "
            f"GARCH={fc.forecast_vol:.4f}  ({direction}{abs(delta):.4f})  "
            f"[{fc.model_used}]"
        )
        if fc.model_used == "garch":
            print(
                f"           α={fc.alpha:.4f} β={fc.beta:.4f} "
                f"persistence={fc.persistence:.4f}"
            )

    print(f"\n  Covariance matrix condition: {np.linalg.cond(cov):.1f}")
    print(f"  Shape: {cov.shape}")


if __name__ == "__main__":
    main()
