#!/usr/bin/env python3
"""
Backtesting Framework for Quantum Portfolio Optimizer.

Simulates historical performance of the QUBO-based portfolio optimization
strategy using rolling windows over historical price data.

Features:
    - Rolling-window QUBO optimization on historical returns
    - Comparison vs. equal-weight & buy-and-hold benchmarks
    - Risk metrics: Sharpe, max drawdown, volatility
    - Configurable rebalancing frequency
    - JSON + terminal output

Usage:
    python backtester.py
    python backtester.py --window 30 --rebalance-days 7 --risk 0.5
    python backtester.py --json-out backtest_result.json

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from quantum.optimizer import Asset, OptimizationResult, PortfolioQUBO, QUBOConfig
from tests.benchmark_optimizer import get_optimizer

logger = logging.getLogger(__name__)

# Try to import httpx for real price fetching
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""

    window_days: int = 30  # lookback window for covariance estimation
    rebalance_days: int = 7  # rebalance every N days
    risk_tolerance: float = 0.5
    target_assets: int = 3
    initial_capital: float = 100_000.0
    transaction_cost_bps: float = 30.0  # 30 bps = 0.3%
    num_days: int = 365  # total simulation period


@dataclass
class BacktestResult:
    """Results of a backtest run."""

    # Strategy performance
    portfolio_values: List[float]
    daily_returns: List[float]
    rebalance_dates: List[int]
    allocations_history: List[Dict[str, float]]

    # Benchmark
    benchmark_values: List[float]  # equal-weight
    buyhold_values: List[float]  # buy-and-hold (first allocation)

    # Metrics
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe_ratio: float
    max_drawdown: float
    num_rebalances: int
    total_transaction_costs: float

    # Benchmark metrics
    benchmark_return: float
    benchmark_sharpe: float
    buyhold_return: float


# ---------------------------------------------------------------------------
# Real historical data fetching (CoinGecko API)
# ---------------------------------------------------------------------------


def fetch_coingecko_prices(
    symbols: Optional[List[str]] = None,
    days: int = 365,
) -> Tuple[Optional[np.ndarray], List[str]]:
    """
    Fetch real historical price data from CoinGecko API.
    
    Args:
        symbols: List of symbols (e.g., ['SUI', 'ETH', 'BTC', 'SOL', 'AVAX'])
        days: Number of historical days to fetch
    
    Returns:
        (prices array shape (days, assets), symbols) or (None, []) if fetch fails
    """
    if not HAS_HTTPX:
        logger.warning("  httpx not available for CoinGecko fetching")
        return None, []

    symbols = symbols or ["SUI", "ETH", "BTC", "SOL", "AVAX"]
    
    # Map symbols to CoinGecko IDs
    coingecko_ids = {
        "SUI": "sui",
        "ETH": "ethereum",
        "BTC": "bitcoin",
        "SOL": "solana",
        "AVAX": "avalanche-2",
    }

    prices_list = []

    for sym in symbols:
        cg_id = coingecko_ids.get(sym, sym.lower())
        url = f"https://api.coingecko.com/api/v3/coins/{cg_id}/market_chart"
        params = {"vs_currency": "usd", "days": str(days), "interval": "daily"}

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                prices = [p[1] for p in data["prices"]]  # Extract [timestamp, price] → price
                prices_list.append(np.array(prices, dtype=np.float64))
                logger.info(f" CoinGecko: {sym} → {len(prices)} days")
        except Exception as e:
            logger.warning(f"  CoinGecko fetch failed for {sym}: {e}")
            return None, []

    if len(prices_list) != len(symbols):
        logger.warning(f"  Not all symbols fetched ({len(prices_list)}/{len(symbols)})")
        return None, []

    # Align all series to same minimum length
    min_len = min(len(p) for p in prices_list)
    prices_array = np.array([p[:min_len] for p in prices_list], dtype=np.float64).T
    logger.info(f" CoinGecko data ready: shape={prices_array.shape}")
    return prices_array, symbols


# ---------------------------------------------------------------------------
# Synthetic price generator (for hackathon demo)
# ---------------------------------------------------------------------------


def generate_synthetic_prices(
    n_assets: int = 5,
    n_days: int = 365,
    seed: int = 42,
) -> Tuple[np.ndarray, List[str]]:
    """
    Generate synthetic daily prices for demo backtesting.
    Uses geometric Brownian motion with realistic crypto parameters.

    Returns:
        prices: (n_days, n_assets) array of daily prices
        symbols: list of asset symbols
    """
    rng = np.random.RandomState(seed)
    symbols = ["SUI", "ETH", "BTC", "SOL", "AVAX"][:n_assets]

    # Annualized parameters (realistic crypto)
    annual_returns = np.array([0.35, 0.20, 0.15, 0.30, 0.25])[:n_assets]
    annual_vols = np.array([0.80, 0.60, 0.45, 0.75, 0.65])[:n_assets]

    # Correlation matrix
    corr = np.array(
        [
            [1.00, 0.55, 0.40, 0.65, 0.50],
            [0.55, 1.00, 0.70, 0.50, 0.45],
            [0.40, 0.70, 1.00, 0.35, 0.30],
            [0.65, 0.50, 0.35, 1.00, 0.55],
            [0.50, 0.45, 0.30, 0.55, 1.00],
        ]
    )[:n_assets, :n_assets]

    # Daily parameters
    dt = 1.0 / 252
    daily_mu = annual_returns * dt
    daily_sigma = annual_vols * np.sqrt(dt)

    # Cholesky decomposition for correlated returns
    L = np.linalg.cholesky(corr)

    # Generate prices via GBM
    prices = np.zeros((n_days, n_assets))
    prices[0] = np.array([1.50, 3500.0, 65000.0, 120.0, 35.0])[:n_assets]

    for t in range(1, n_days):
        z = rng.randn(n_assets)
        correlated_z = L @ z
        log_returns = daily_mu - 0.5 * daily_sigma**2 + daily_sigma * correlated_z
        prices[t] = prices[t - 1] * np.exp(log_returns)

    return prices, symbols


# ---------------------------------------------------------------------------
# Backtester
# ---------------------------------------------------------------------------


class Backtester:
    """Rolling-window QUBO portfolio backtester."""

    def __init__(
        self,
        prices: np.ndarray,
        symbols: List[str],
        config: Optional[BacktestConfig] = None,
    ):
        self.prices = prices  # (n_days, n_assets)
        self.symbols = symbols
        self.n_days, self.n_assets = prices.shape
        self.cfg = config or BacktestConfig()

        assert len(symbols) == self.n_assets

    def _compute_returns(self, start: int, end: int) -> np.ndarray:
        """Compute daily log returns for a window."""
        window_prices = self.prices[start:end]
        return np.diff(np.log(window_prices), axis=0)

    def _estimate_params(
        self, returns: np.ndarray
    ) -> Tuple[List[Asset], np.ndarray]:
        """Estimate expected returns and covariance from historical returns."""
        mu = np.mean(returns, axis=0) * 252  # annualize
        cov = np.cov(returns, rowvar=False) * 252  # annualize

        assets = [
            Asset(
                symbol=self.symbols[i],
                expected_return=float(mu[i]),
                max_weight=0.40,
            )
            for i in range(self.n_assets)
        ]
        return assets, cov

    def run(self) -> BacktestResult:
        """Execute the full backtest."""
        cfg = self.cfg
        window = cfg.window_days
        capital = cfg.initial_capital
        tx_cost_rate = cfg.transaction_cost_bps / 10_000

        # Initialize
        portfolio_values = [capital]
        daily_returns_list = []
        rebalance_dates = []
        allocations_history = []
        total_tx_costs = 0.0

        # Current weights (start equal)
        weights = np.ones(self.n_assets) / self.n_assets
        last_rebalance = window

        # Benchmark: equal-weight (rebalanced daily)
        eq_capital = capital
        eq_values = [capital]

        # Buy-and-hold benchmark
        bh_capital = capital
        bh_weights = weights.copy()
        bh_values = [capital]

        for day in range(window, self.n_days - 1):
            # Daily price returns
            daily_ret = self.prices[day + 1] / self.prices[day] - 1.0

            # ── Strategy portfolio update ──
            port_return = np.dot(weights, daily_ret)
            capital *= 1.0 + port_return
            portfolio_values.append(capital)
            daily_returns_list.append(port_return)

            # ── Equal-weight benchmark ──
            eq_return = np.mean(daily_ret)
            eq_capital *= 1.0 + eq_return
            eq_values.append(eq_capital)

            # ── Buy-and-hold benchmark ──
            bh_return = np.dot(bh_weights, daily_ret)
            bh_capital *= 1.0 + bh_return
            bh_values.append(bh_capital)
            # Update buy-hold weights for drift
            bh_weights = bh_weights * (1.0 + daily_ret)
            bh_weights /= bh_weights.sum()

            # ── Rebalance check ──
            if day - last_rebalance >= cfg.rebalance_days:
                returns = self._compute_returns(day - window, day)
                if len(returns) < 5:
                    continue

                try:
                    assets, cov = self._estimate_params(returns)

                    qubo_cfg = QUBOConfig(
                        lambda_return=1.0,
                        lambda_risk=max(0.1, 1.0 - cfg.risk_tolerance),
                        lambda_budget=2.0,
                        target_assets=cfg.target_assets,
                    )
                    optimizer = PortfolioQUBO(assets, cov, qubo_cfg)
                    result = optimizer.solve()

                    new_weights = np.array(
                        [result.weights.get(s, 0.0) for s in self.symbols]
                    )

                    # Transaction cost
                    turnover = np.sum(np.abs(new_weights - weights))
                    cost = turnover * tx_cost_rate * capital
                    capital -= cost
                    total_tx_costs += cost

                    weights = new_weights
                    last_rebalance = day
                    rebalance_dates.append(day)
                    allocations_history.append(
                        {s: float(w) for s, w in zip(self.symbols, weights)}
                    )

                except Exception as e:
                    logger.warning(f"Rebalance failed at day {day}: {e}")

        # ── Compute metrics ──
        returns_arr = np.array(daily_returns_list)
        total_return = (capital / cfg.initial_capital) - 1.0
        ann_return = (1.0 + total_return) ** (252 / max(len(returns_arr), 1)) - 1.0
        ann_vol = np.std(returns_arr) * np.sqrt(252) if len(returns_arr) > 0 else 0.0
        sharpe = ann_return / ann_vol if ann_vol > 0 else 0.0

        # Max drawdown
        cum_values = np.array(portfolio_values)
        running_max = np.maximum.accumulate(cum_values)
        drawdowns = (cum_values - running_max) / running_max
        max_dd = float(np.min(drawdowns))

        # Benchmark metrics
        bench_total = (eq_capital / cfg.initial_capital) - 1.0
        eq_returns = np.diff(np.array(eq_values)) / np.array(eq_values[:-1])
        bench_vol = np.std(eq_returns) * np.sqrt(252) if len(eq_returns) > 0 else 0.0
        bench_ann = (1.0 + bench_total) ** (252 / max(len(eq_returns), 1)) - 1.0
        bench_sharpe = bench_ann / bench_vol if bench_vol > 0 else 0.0

        bh_total = (bh_capital / cfg.initial_capital) - 1.0

        return BacktestResult(
            portfolio_values=portfolio_values,
            daily_returns=daily_returns_list,
            rebalance_dates=rebalance_dates,
            allocations_history=allocations_history,
            benchmark_values=eq_values,
            buyhold_values=bh_values,
            total_return=total_return,
            annualized_return=ann_return,
            annualized_volatility=ann_vol,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            num_rebalances=len(rebalance_dates),
            total_transaction_costs=total_tx_costs,
            benchmark_return=bench_total,
            benchmark_sharpe=bench_sharpe,
            buyhold_return=bh_total,
        )


# ---------------------------------------------------------------------------
# Benchmark comparison function
# ---------------------------------------------------------------------------


def compare_optimizers(
    prices: np.ndarray,
    symbols: List[str],
    config: BacktestConfig,
) -> Dict[str, Dict[str, float]]:
    """
    Compare QUBO optimizer against classical optimizers.

    Args:
        prices: (n_days, n_assets) price array
        symbols: asset symbols
        config: backtest configuration

    Returns:
        Dictionary with results for each optimizer
    """
    logger.info(" COMPARING OPTIMIZERS")
    logger.info("━" * 60)

    results = {}
    optimizers = ["qubo", "markowitz", "equal-weight", "hrp", "buy-hold"]

    for opt_name in optimizers:
        logger.info(f"  Testing {opt_name}...")

        if opt_name == "qubo":
            # Use main QUBO backtester
            bt = Backtester(prices, symbols, config)
            result = bt.run()
            results[opt_name] = {
                "total_return": result.total_return,
                "ann_return": result.annualized_return,
                "ann_vol": result.annualized_volatility,
                "sharpe": result.sharpe_ratio,
                "max_dd": result.max_drawdown,
                "rebalances": result.num_rebalances,
                "tx_costs": result.total_transaction_costs,
            }
        else:
            # Use classical optimizer
            opt = get_optimizer(opt_name, symbols, window_days=config.window_days)

            # Simple rolling-window backtest
            daily_values = [config.initial_capital]
            daily_returns = []

            for day in range(config.window_days, len(prices)):
                # Get window of returns
                window_prices = prices[day - config.window_days : day]
                window_returns = np.diff(window_prices, axis=0) / window_prices[:-1]

                # Optimize
                weights_dict, exp_ret, exp_vol = opt.optimize(window_returns)
                weights = np.array([weights_dict[sym] for sym in symbols])

                # Daily return
                day_ret = np.diff(prices[day - 1 : day + 1], axis=0) / prices[day - 1]
                port_ret = (weights * day_ret.flatten()).sum()
                daily_returns.append(port_ret)

                # Portfolio value
                daily_values.append(daily_values[-1] * (1 + port_ret))

            # Metrics
            daily_returns_arr = np.array(daily_returns)
            total_ret = (daily_values[-1] / config.initial_capital) - 1.0
            ann_ret = (1 + total_ret) ** (252 / len(daily_returns)) - 1.0
            ann_vol = np.std(daily_returns_arr) * np.sqrt(252)
            sharpe = ann_ret / ann_vol if ann_vol > 0 else 0.0

            # Max drawdown
            cumulative = np.array(daily_values)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_dd = np.min(drawdown) if len(drawdown) > 0 else 0.0

            results[opt_name] = {
                "total_return": total_ret,
                "ann_return": ann_ret,
                "ann_vol": ann_vol,
                "sharpe": sharpe,
                "max_dd": max_dd,
                "rebalances": 0,
                "tx_costs": 0,
            }

    # Print comparison table
    logger.info("")
    logger.info("BENCHMARK RESULTS")
    logger.info("━" * 100)
    logger.info(
        f"{'Optimizer':20s} {'Total Return':>15s} {'Ann. Return':>15s} {'Ann. Vol':>12s} {'Sharpe':>10s} {'Max DD':>12s}"
    )
    logger.info("━" * 100)

    qubo_sharpe = results["qubo"]["sharpe"]
    for opt_name, metrics in results.items():
        alpha = (
            metrics["sharpe"] - qubo_sharpe
            if opt_name != "qubo"
            else 0.0
        )
        alpha_str = f"({alpha:+.3f})" if alpha != 0.0 else ""
        logger.info(
            f"{opt_name:20s} {metrics['total_return']:15.2%} {metrics['ann_return']:15.2%} "
            f"{metrics['ann_vol']:12.2%} {metrics['sharpe']:10.3f} {metrics['max_dd']:12.2%}"
        )

    logger.info("━" * 100)
    logger.info(" Benchmark complete")

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(description="QUBO Portfolio Backtester")
    parser.add_argument("--window", type=int, default=30, help="Lookback window (days)")
    parser.add_argument("--rebalance-days", type=int, default=7, help="Rebalance frequency")
    parser.add_argument("--risk", type=float, default=0.5, help="Risk tolerance 0-1")
    parser.add_argument("--target", type=int, default=3, help="Target number of assets")
    parser.add_argument("--days", type=int, default=365, help="Simulation period (days)")
    parser.add_argument("--capital", type=float, default=100_000, help="Initial capital")
    parser.add_argument("--real-data", action="store_true", help="Fetch real CoinGecko prices")
    parser.add_argument("--benchmark", action="store_true", help="Compare against classical optimizers")
    parser.add_argument("--json-out", type=str, help="Write results to JSON file")
    args = parser.parse_args()

    print()
    print("╔══════════════════════════════════════════════════════╗")
    print("║   QUANTUM PORTFOLIO BACKTESTER   —   CashXChain     ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()

    cfg = BacktestConfig(
        window_days=args.window,
        rebalance_days=args.rebalance_days,
        risk_tolerance=args.risk,
        target_assets=args.target,
        num_days=args.days,
        initial_capital=args.capital,
    )

    print(f"  Config: window={cfg.window_days}d, rebalance={cfg.rebalance_days}d, "
          f"risk={cfg.risk_tolerance}, target={cfg.target_assets} assets")
    print(f"  Capital: ${cfg.initial_capital:,.0f}, Period: {cfg.num_days} days")
    print()

    # Fetch real or synthetic data
    if args.real_data:
        print("   Fetching real CoinGecko price data...")
        prices, symbols = fetch_coingecko_prices(days=cfg.num_days)
        if prices is None:
            print("    CoinGecko fetch failed, falling back to synthetic data")
            prices, symbols = generate_synthetic_prices(n_days=cfg.num_days)
        else:
            print(f"   Real data loaded: {prices.shape[0]} days for {symbols}")
    else:
        print("  Generating synthetic price data...")
        prices, symbols = generate_synthetic_prices(n_days=cfg.num_days)
        print(f"  Generated {cfg.num_days} days of synthetic price data for {symbols}")


    t0 = time.perf_counter()
    bt = Backtester(prices, symbols, cfg)
    result = bt.run()
    elapsed = time.perf_counter() - t0

    print(f"\n── Results ({elapsed:.2f}s) ─────────────────────────────────")
    print(f"  Strategy:")
    print(f"    Total Return     : {result.total_return:+.2%}")
    print(f"    Ann. Return      : {result.annualized_return:+.2%}")
    print(f"    Ann. Volatility  : {result.annualized_volatility:.2%}")
    print(f"    Sharpe Ratio     : {result.sharpe_ratio:.3f}")
    print(f"    Max Drawdown     : {result.max_drawdown:.2%}")
    print(f"    Rebalances       : {result.num_rebalances}")
    print(f"    Transaction Costs: ${result.total_transaction_costs:,.2f}")
    print()
    print(f"  Benchmarks:")
    print(f"    Equal-Weight     : {result.benchmark_return:+.2%} (Sharpe: {result.benchmark_sharpe:.3f})")
    print(f"    Buy-and-Hold     : {result.buyhold_return:+.2%}")
    print()

    alpha = result.total_return - result.benchmark_return
    print(f"  Alpha vs Equal-Weight: {alpha:+.2%}")

    # Benchmark comparison
    if args.benchmark:
        print()
        benchmark_results = compare_optimizers(prices, symbols, cfg)
        print()
        print(" Benchmark comparison saved")


    if result.allocations_history:
        print(f"\n  Last Allocation:")
        for sym, w in result.allocations_history[-1].items():
            print(f"    {sym:6s}  {w:6.1%}")

    if args.json_out:
        out = {
            "config": {
                "window_days": cfg.window_days,
                "rebalance_days": cfg.rebalance_days,
                "risk_tolerance": cfg.risk_tolerance,
                "target_assets": cfg.target_assets,
                "initial_capital": cfg.initial_capital,
                "num_days": cfg.num_days,
            },
            "metrics": {
                "total_return": result.total_return,
                "annualized_return": result.annualized_return,
                "annualized_volatility": result.annualized_volatility,
                "sharpe_ratio": result.sharpe_ratio,
                "max_drawdown": result.max_drawdown,
                "num_rebalances": result.num_rebalances,
                "transaction_costs": result.total_transaction_costs,
            },
            "benchmarks": {
                "equal_weight_return": result.benchmark_return,
                "equal_weight_sharpe": result.benchmark_sharpe,
                "buyhold_return": result.buyhold_return,
            },
            "allocations_history": result.allocations_history,
            "elapsed_s": elapsed,
        }
        with open(args.json_out, "w") as f:
            json.dump(out, f, indent=2)
        print(f"\n   Results saved to {args.json_out}")

    print("\n Done.\n")


if __name__ == "__main__":
    main()

