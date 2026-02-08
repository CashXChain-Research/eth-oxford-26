#!/usr/bin/env python3
"""
Market Impact & Slippage Model for Portfolio Rebalancing.

Estimates the price impact of each swap using the Almgren–Chriss
market impact model (simplified):

    Impact = α · (OrderSize / DailyVolume) ^ β

Where:
    α (alpha) = market impact coefficient (calibrated per asset class)
    β (beta)  = impact exponent (typically 0.5–0.8 for crypto)
    OrderSize = trade amount in USD
    DailyVolume = 24h trading volume in USD

The result is a percentage slippage that gets converted to a `min_out`
value for on-chain enforcement:

    min_out = order_size * (1 - impact_pct - safety_margin)

The Move contract's `atomic_rebalance` function checks:
    assert!(output >= min_out, ESlippageExceeded)

If the DEX returns less than min_out for ANY swap, the entire
transaction block reverts atomically. This is what makes the
"Atomic Rebalancing" actually valuable — not just a buzzword.

References:
    - Almgren & Chriss (2001): "Optimal execution of portfolio transactions"
    - Cont, Kukanov & Stoikov (2014): "The Price Impact of Order Book Events"

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ── Impact Model Parameters ──────────────────────────
# Calibrated for crypto markets (higher α than TradFi due to
# thinner order books and higher volatility)

@dataclass
class ImpactParams:
    """Market impact model parameters per asset class."""
    alpha: float = 0.10     # impact coefficient (10% baseline for crypto)
    beta: float = 0.60      # impact exponent (sub-linear: sqrt-like)
    safety_margin_bps: int = 50  # extra 0.5% buffer beyond estimated impact
    max_impact_pct: float = 0.05  # hard cap: reject trades with >5% impact


# Asset-specific calibrations (crypto markets are heterogeneous)
ASSET_IMPACT_PARAMS: Dict[str, ImpactParams] = {
    "BTC":  ImpactParams(alpha=0.05, beta=0.55),    # deep liquidity
    "ETH":  ImpactParams(alpha=0.06, beta=0.55),    # deep liquidity
    "SUI":  ImpactParams(alpha=0.12, beta=0.65),    # thinner books
    "SOL":  ImpactParams(alpha=0.08, beta=0.60),    # medium liquidity
    "AVAX": ImpactParams(alpha=0.10, beta=0.60),    # medium liquidity
}

DEFAULT_PARAMS = ImpactParams()

# ── Mock 24h volumes (USD) for demo ──────────────────
# In production: fetch from CoinGecko /coins/{id}/market_chart
MOCK_DAILY_VOLUMES: Dict[str, float] = {
    "BTC":  25_000_000_000,  # $25B
    "ETH":  12_000_000_000,  # $12B
    "SUI":     400_000_000,  # $400M
    "SOL":   2_500_000_000,  # $2.5B
    "AVAX":    300_000_000,  # $300M
}


@dataclass
class SlippageEstimate:
    """Estimated slippage for a single swap."""
    symbol: str
    order_size_usd: float
    daily_volume_usd: float
    # Model outputs
    volume_fraction: float   # OrderSize / DailyVolume
    raw_impact_pct: float    # α · (fraction)^β
    safety_margin_pct: float # additional buffer
    total_slippage_pct: float  # raw + safety
    min_out_usd: float       # order_size * (1 - total_slippage)
    min_out_mist: int        # min_out in smallest on-chain unit
    # Model params used
    alpha: float
    beta: float
    # Flags
    exceeds_max_impact: bool  # true if impact > max_impact_pct
    model_used: str = "almgren_chriss"


def estimate_market_impact(
    symbol: str,
    order_size_usd: float,
    daily_volume_usd: Optional[float] = None,
    params: Optional[ImpactParams] = None,
    sui_price_usd: float = 1.0,
) -> SlippageEstimate:
    """
    Estimate market impact for a single swap using the Almgren–Chriss model.

    Impact = α · (OrderSize / DailyVolume) ^ β

    Args:
        symbol: Asset symbol (e.g., "SUI", "BTC")
        order_size_usd: Trade size in USD
        daily_volume_usd: 24h volume in USD (None = use mock)
        params: Override impact parameters
        sui_price_usd: SUI price for MIST conversion

    Returns:
        SlippageEstimate with impact percentage and min_out values
    """
    p = params or ASSET_IMPACT_PARAMS.get(symbol, DEFAULT_PARAMS)
    volume = daily_volume_usd or MOCK_DAILY_VOLUMES.get(symbol, 500_000_000)

    # Volume fraction
    fraction = order_size_usd / volume if volume > 0 else 1.0

    # Almgren–Chriss impact: α · (V/ADV)^β
    raw_impact = p.alpha * (fraction ** p.beta)

    # Safety margin (convert BPS to decimal)
    safety = p.safety_margin_bps / 10_000

    # Total expected slippage
    total_slip = raw_impact + safety

    # Exceeds hard cap?
    exceeds = raw_impact > p.max_impact_pct

    # min_out in USD
    min_out_usd = order_size_usd * (1.0 - total_slip)

    # Convert to MIST (SUI smallest unit, 1 SUI = 10^9 MIST)
    min_out_sui = min_out_usd / sui_price_usd if sui_price_usd > 0 else 0
    min_out_mist = int(min_out_sui * 1_000_000_000)

    estimate = SlippageEstimate(
        symbol=symbol,
        order_size_usd=order_size_usd,
        daily_volume_usd=volume,
        volume_fraction=fraction,
        raw_impact_pct=raw_impact,
        safety_margin_pct=safety,
        total_slippage_pct=total_slip,
        min_out_usd=min_out_usd,
        min_out_mist=max(0, min_out_mist),
        alpha=p.alpha,
        beta=p.beta,
        exceeds_max_impact=exceeds,
    )

    logger.info(
        f"[{symbol}] Impact: {raw_impact:.4%} "
        f"(α={p.alpha}, β={p.beta}, V/ADV={fraction:.6f}) "
        f"→ total slip={total_slip:.4%}, min_out=${min_out_usd:,.2f}"
    )

    return estimate


def estimate_rebalance_slippage(
    allocation: Dict[str, int],
    weights: Dict[str, float],
    portfolio_value_usd: float = 50_000,
    daily_volumes: Optional[Dict[str, float]] = None,
    sui_price_usd: float = 1.0,
) -> Dict[str, SlippageEstimate]:
    """
    Estimate slippage for an entire rebalance (multiple swaps).

    Called by the ExecutionAgent after QUBO optimization to compute
    min_out values for every selected asset before submitting to chain.

    Args:
        allocation: {symbol: 0|1} — which assets are selected
        weights: {symbol: float} — target weights (sum ≈ 1.0)
        portfolio_value_usd: Total portfolio value
        daily_volumes: Override 24h volumes per asset
        sui_price_usd: SUI/USD price for on-chain unit conversion

    Returns:
        Dict of SlippageEstimates keyed by symbol (only selected assets)
    """
    estimates: Dict[str, SlippageEstimate] = {}

    for symbol, selected in allocation.items():
        if selected != 1:
            continue

        weight = weights.get(symbol, 0)
        if weight <= 0:
            continue

        order_size = portfolio_value_usd * weight
        volume = (daily_volumes or {}).get(symbol)

        estimates[symbol] = estimate_market_impact(
            symbol=symbol,
            order_size_usd=order_size,
            daily_volume_usd=volume,
            sui_price_usd=sui_price_usd,
        )

    # Log aggregate
    total_order = sum(e.order_size_usd for e in estimates.values())
    avg_slip = (
        np.mean([e.total_slippage_pct for e in estimates.values()])
        if estimates else 0
    )
    any_exceeds = any(e.exceeds_max_impact for e in estimates.values())

    logger.info(
        f"Rebalance slippage: {len(estimates)} swaps, "
        f"total=${total_order:,.0f}, avg slip={avg_slip:.4%}, "
        f"any_exceeds_max={any_exceeds}"
    )

    return estimates


def build_swap_min_outputs(
    estimates: Dict[str, SlippageEstimate],
) -> tuple:
    """
    Convert slippage estimates to the vectors needed by
    atomic_rebalance(swap_amounts, swap_min_outputs).

    Returns:
        (symbols, swap_amounts_mist, swap_min_outputs_mist)
    """
    symbols = []
    amounts = []
    min_outputs = []

    for sym, est in estimates.items():
        symbols.append(sym)
        # Amount in MIST
        amount_mist = int(est.order_size_usd / 1.0 * 1_000_000_000)  # placeholder price
        amounts.append(amount_mist)
        min_outputs.append(est.min_out_mist)

    return symbols, amounts, min_outputs


def format_slippage_report(estimates: Dict[str, SlippageEstimate]) -> str:
    """Format a human-readable slippage report for agent logs."""
    lines = ["Market Impact Analysis (Almgren-Chriss):"]
    for sym, e in estimates.items():
        status = "EXCEEDS MAX" if e.exceeds_max_impact else "OK"
        lines.append(
            f"  {sym:6s}  order=${e.order_size_usd:>10,.0f}  "
            f"V/ADV={e.volume_fraction:.6f}  "
            f"impact={e.raw_impact_pct:.4%}  "
            f"min_out=${e.min_out_usd:>10,.0f}  [{status}]"
        )
    return "\n".join(lines)


# ── CLI test ─────────────────────────────────────────


def main():
    """Quick demonstration of the impact model."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("\n── Market Impact Model (Almgren-Chriss) ──\n")

    # Simulate a $50K portfolio rebalance
    allocation = {"SUI": 1, "BTC": 1, "ETH": 1, "SOL": 0, "AVAX": 1}
    weights = {"SUI": 0.30, "BTC": 0.25, "ETH": 0.25, "SOL": 0.0, "AVAX": 0.20}

    for portfolio_value in [10_000, 50_000, 500_000, 5_000_000]:
        print(f"\n  Portfolio: ${portfolio_value:,.0f}")
        print(f"  {'='*70}")

        estimates = estimate_rebalance_slippage(
            allocation=allocation,
            weights=weights,
            portfolio_value_usd=portfolio_value,
        )

        for sym, e in estimates.items():
            status = "REJECT" if e.exceeds_max_impact else "OK"
            print(
                f"  {sym:6s}  ${e.order_size_usd:>10,.0f}  "
                f"impact={e.raw_impact_pct:>7.3%}  "
                f"slip={e.total_slippage_pct:>7.3%}  "
                f"min_out=${e.min_out_usd:>10,.0f}  [{status}]"
            )

        total_impact_cost = sum(
            e.order_size_usd * e.raw_impact_pct for e in estimates.values()
        )
        print(f"  Total impact cost: ${total_impact_cost:,.2f}")


if __name__ == "__main__":
    main()
