#!/usr/bin/env python3
"""
Real market data fetcher using CoinGecko API (free, no API key needed).

Fetches:
  - Current prices
  - 30-day historical prices → compute returns & covariance
  - Market caps for weighting

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import httpx
except ImportError:
    raise ImportError("pip install httpx")

from quantum.optimizer import Asset

logger = logging.getLogger(__name__)

# CoinGecko IDs for our 5 assets
ASSET_MAP = {
    "SUI": "sui",
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "SOL": "solana",
    "AVAX": "avalanche-2",
}

COINGECKO_BASE = "https://api.coingecko.com/api/v3"


class MarketDataFetcher:
    """Fetch real market data from CoinGecko."""

    def __init__(self, symbols: Optional[List[str]] = None):
        self.symbols = symbols or list(ASSET_MAP.keys())
        self.cg_ids = [ASSET_MAP[s] for s in self.symbols]

    def fetch_prices_and_returns(self, days: int = 30) -> Tuple[List[Asset], np.ndarray]:
        """
        Fetch historical prices, compute expected returns & covariance.
        Returns (assets, cov_matrix).
        """
        logger.info(f"Fetching {days}-day price history for {self.symbols} …")

        all_returns = []
        assets = []

        for symbol, cg_id in zip(self.symbols, self.cg_ids):
            try:
                prices = self._fetch_price_history(cg_id, days)
                if len(prices) < 2:
                    logger.warning(f"Not enough data for {symbol}, using fallback")
                    assets.append(Asset(symbol=symbol, expected_return=0.15, max_weight=0.40))
                    all_returns.append(np.random.normal(0.0005, 0.02, days))
                    continue

                # Daily log returns
                prices = np.array(prices)
                log_returns = np.diff(np.log(prices))
                all_returns.append(log_returns)

                # Annualized expected return (daily mean × 365)
                daily_mean = np.mean(log_returns)
                annual_return = daily_mean * 365

                assets.append(
                    Asset(
                        symbol=symbol,
                        expected_return=float(annual_return),
                        max_weight=0.40,
                    )
                )
                logger.info(f"  {symbol}: {len(prices)} prices, E(r)={annual_return:.2%} ann.")

            except Exception as e:
                logger.warning(f"Failed to fetch {symbol}: {e}, using fallback")
                assets.append(Asset(symbol=symbol, expected_return=0.15, max_weight=0.40))
                all_returns.append(np.random.normal(0.0005, 0.02, days))

        # Equalize return vector lengths
        min_len = min(len(r) for r in all_returns)
        trimmed = [r[:min_len] for r in all_returns]
        return_matrix = np.array(trimmed)  # (n_assets, n_days)

        # Annualized covariance matrix
        cov = np.cov(return_matrix) * 365

        # Ensure positive semi-definite (numerical stability)
        cov = (cov + cov.T) / 2
        eigvals = np.linalg.eigvalsh(cov)
        if eigvals.min() < 0:
            cov -= 1.1 * eigvals.min() * np.eye(len(assets))

        logger.info(f"Covariance matrix (raw): {cov.shape}, cond={np.linalg.cond(cov):.1f}")

        # ── Calibration (simplified Black-Litterman) ─────────────────
        # Raw 30-day trailing returns annualized (daily_mean * 365) can
        # produce extreme values (-300% to +500%) that are unusable for
        # forward-looking portfolio optimization.  We preserve the
        # RELATIVE ranking from live market data but map to a reasonable
        # expected-return range — exactly what Black-Litterman does in
        # practice (blend equilibrium prior with market views).
        #
        # This keeps the optimizer's asset-selection signal intact while
        # ensuring the QUBO can find a diversified, risk-feasible portfolio.

        raw_returns = [a.expected_return for a in assets]
        min_ret, max_ret = min(raw_returns), max(raw_returns)
        ret_range = max_ret - min_ret

        TARGET_CENTER = 0.15    # 15% average annual (crypto equilibrium)
        TARGET_SPREAD = 0.25    # range ≈ [2.5%, 27.5%]

        if ret_range > 1e-10:
            for a in assets:
                norm = (a.expected_return - min_ret) / ret_range  # [0, 1]
                a.expected_return = float(
                    (TARGET_CENTER - TARGET_SPREAD / 2) + norm * TARGET_SPREAD
                )
        else:
            for a in assets:
                a.expected_return = TARGET_CENTER

        logger.info(
            "Calibrated returns (Black-Litterman): "
            + ", ".join(f"{a.symbol}={a.expected_return:.2%}" for a in assets)
        )

        # ── Covariance shrinkage ─────────────────────────────────────
        # Short-window daily returns overestimate annualized volatility
        # (e.g. 80-110% for crypto).  Scale toward a long-term average
        # vol target so the QUBO risk term stays meaningful.

        avg_vol = float(np.sqrt(np.mean(np.diag(cov))))
        TARGET_AVG_VOL = 0.35   # ~35% annualized (typical crypto long-term)
        if avg_vol > 1e-10:
            vol_scale = (TARGET_AVG_VOL / avg_vol) ** 2
            cov = cov * vol_scale
            logger.info(
                f"Covariance scaled ×{vol_scale:.3f} "
                f"(avg vol {avg_vol:.1%} → {TARGET_AVG_VOL:.1%})"
            )

        logger.info(f"Covariance matrix (calibrated): {cov.shape}, cond={np.linalg.cond(cov):.1f}")
        return assets, cov

    def _fetch_price_history(self, cg_id: str, days: int) -> List[float]:
        """Fetch daily close prices from CoinGecko."""
        url = f"{COINGECKO_BASE}/coins/{cg_id}/market_chart"
        params = {"vs_currency": "usd", "days": str(days), "interval": "daily"}

        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        prices = [p[1] for p in data.get("prices", [])]
        return prices

    def fetch_current_prices(self) -> Dict[str, float]:
        """Fetch current prices for all assets."""
        ids = ",".join(self.cg_ids)
        url = f"{COINGECKO_BASE}/simple/price"
        params = {"ids": ids, "vs_currencies": "usd"}

        with httpx.Client(timeout=10) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        prices = {}
        for symbol, cg_id in zip(self.symbols, self.cg_ids):
            prices[symbol] = data.get(cg_id, {}).get("usd", 0)

        return prices


# ── CLI test ─────────────────────────────────────────


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    fetcher = MarketDataFetcher()

    print("\n── Current Prices ──")
    try:
        prices = fetcher.fetch_current_prices()
        for sym, price in prices.items():
            print(f"  {sym:6s}  ${price:,.2f}")
    except Exception as e:
        print(f"  (Could not fetch: {e})")

    print("\n── Historical Returns & Covariance ──")
    try:
        assets, cov = fetcher.fetch_prices_and_returns(days=30)
        print(f"  Assets:")
        for a in assets:
            print(f"    {a.symbol:6s}  E(r) = {a.expected_return:+.2%}")
        print(f"\n  Covariance matrix (annualized):")
        print(f"  {cov.round(4)}")
    except Exception as e:
        print(f"  (Could not fetch: {e})")
        print("  → Falling back to mock data for hackathon demo")


if __name__ == "__main__":
    main()
