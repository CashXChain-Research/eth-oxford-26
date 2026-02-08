#!/usr/bin/env python3
"""
Tests for the market impact / slippage model.

Validates:
  - Almgren-Chriss formula correctness
  - Impact scales non-linearly with order size
  - min_out < order_size always
  - Large orders correctly flagged as exceeding max impact
  - Rebalance-level slippage aggregation
  - Edge cases (zero volume, unknown assets)

Run:
    python -m pytest tests/test_slippage.py -v
"""

import unittest

import numpy as np

from core.slippage import (
    ASSET_IMPACT_PARAMS,
    MOCK_DAILY_VOLUMES,
    ImpactParams,
    SlippageEstimate,
    estimate_market_impact,
    estimate_rebalance_slippage,
    build_swap_min_outputs,
    format_slippage_report,
)


class TestAlmgrenChrissModel(unittest.TestCase):
    """Test the core Impact = α · (V/ADV)^β formula."""

    def test_basic_formula(self):
        """Impact = 0.10 * (1000/1e9)^0.60 for default params."""
        est = estimate_market_impact(
            symbol="TEST",
            order_size_usd=1000,
            daily_volume_usd=1_000_000_000,
            params=ImpactParams(alpha=0.10, beta=0.60, safety_margin_bps=0),
        )
        # fraction = 1e-6, impact = 0.10 * (1e-6)^0.60
        expected = 0.10 * (1e-6) ** 0.60
        self.assertAlmostEqual(est.raw_impact_pct, expected, places=8)

    def test_impact_increases_with_order_size(self):
        """Larger orders should have higher impact."""
        small = estimate_market_impact("BTC", order_size_usd=10_000)
        large = estimate_market_impact("BTC", order_size_usd=1_000_000)
        self.assertGreater(large.raw_impact_pct, small.raw_impact_pct)

    def test_impact_sub_linear(self):
        """Impact should grow sub-linearly (β < 1)."""
        e1 = estimate_market_impact("BTC", order_size_usd=100_000)
        e10 = estimate_market_impact("BTC", order_size_usd=1_000_000)
        # 10x order should give < 10x impact (sub-linear)
        ratio = e10.raw_impact_pct / e1.raw_impact_pct
        self.assertLess(ratio, 10.0)
        self.assertGreater(ratio, 1.0)

    def test_min_out_less_than_order(self):
        """min_out should always be less than order size."""
        est = estimate_market_impact("SUI", order_size_usd=50_000)
        self.assertLess(est.min_out_usd, 50_000)
        self.assertGreater(est.min_out_usd, 0)

    def test_min_out_mist_positive(self):
        """MIST-denominated min_out should be positive."""
        est = estimate_market_impact("ETH", order_size_usd=10_000)
        self.assertGreater(est.min_out_mist, 0)

    def test_safety_margin_included(self):
        """Total slippage should be raw impact + safety margin."""
        est = estimate_market_impact(
            "TEST",
            order_size_usd=10_000,
            daily_volume_usd=1e9,
            params=ImpactParams(alpha=0.10, beta=0.60, safety_margin_bps=100),
        )
        # safety = 100 bps = 1%
        expected_total = est.raw_impact_pct + 0.01
        self.assertAlmostEqual(est.total_slippage_pct, expected_total, places=8)

    def test_exceeds_max_impact_flag(self):
        """Very large order should trigger exceeds_max_impact."""
        est = estimate_market_impact(
            "TEST",
            order_size_usd=100_000_000,
            daily_volume_usd=50_000_000,
            params=ImpactParams(alpha=0.50, beta=0.50, max_impact_pct=0.05),
        )
        # fraction = 2.0, impact = 0.50 * (2.0)^0.50 = 0.707 > 5%
        self.assertTrue(est.exceeds_max_impact)

    def test_small_order_no_exceed(self):
        """Small orders should not exceed max impact."""
        est = estimate_market_impact("BTC", order_size_usd=1_000)
        self.assertFalse(est.exceeds_max_impact)


class TestAssetCalibrations(unittest.TestCase):
    """Test that per-asset parameters produce reasonable results."""

    def test_btc_lower_impact_than_sui(self):
        """BTC (deeper liquidity) should have lower impact than SUI."""
        btc = estimate_market_impact("BTC", order_size_usd=100_000)
        sui = estimate_market_impact("SUI", order_size_usd=100_000)
        self.assertLess(btc.raw_impact_pct, sui.raw_impact_pct)

    def test_all_configured_assets(self):
        """All 5 assets should have valid calibrations."""
        for symbol in ["BTC", "ETH", "SUI", "SOL", "AVAX"]:
            est = estimate_market_impact(symbol, order_size_usd=50_000)
            self.assertGreater(est.raw_impact_pct, 0)
            self.assertIn(symbol, ASSET_IMPACT_PARAMS)
            self.assertIn(symbol, MOCK_DAILY_VOLUMES)

    def test_unknown_asset_uses_defaults(self):
        """Unknown asset falls back to DEFAULT_PARAMS."""
        est = estimate_market_impact("DOGE", order_size_usd=10_000)
        self.assertGreater(est.raw_impact_pct, 0)
        self.assertEqual(est.alpha, 0.10)  # DEFAULT_PARAMS


class TestRebalanceSlippage(unittest.TestCase):
    """Test portfolio-level slippage estimation."""

    def setUp(self):
        self.allocation = {"SUI": 1, "BTC": 1, "ETH": 1, "SOL": 0, "AVAX": 1}
        self.weights = {"SUI": 0.30, "BTC": 0.25, "ETH": 0.25, "SOL": 0.0, "AVAX": 0.20}

    def test_only_selected_assets(self):
        """Only assets with allocation=1 should have estimates."""
        estimates = estimate_rebalance_slippage(
            self.allocation,
            self.weights,
            portfolio_value_usd=50_000,
        )
        self.assertIn("SUI", estimates)
        self.assertIn("BTC", estimates)
        self.assertNotIn("SOL", estimates)  # SOL is 0

    def test_order_sizes_match_weights(self):
        """Order sizes should reflect weight * portfolio value."""
        estimates = estimate_rebalance_slippage(
            self.allocation,
            self.weights,
            portfolio_value_usd=100_000,
        )
        self.assertAlmostEqual(estimates["SUI"].order_size_usd, 30_000, places=0)
        self.assertAlmostEqual(estimates["BTC"].order_size_usd, 25_000, places=0)

    def test_build_swap_min_outputs(self):
        """build_swap_min_outputs returns valid vectors."""
        estimates = estimate_rebalance_slippage(
            self.allocation,
            self.weights,
            portfolio_value_usd=50_000,
        )
        symbols, amounts, min_outputs = build_swap_min_outputs(estimates)
        self.assertEqual(len(symbols), 4)
        self.assertEqual(len(amounts), 4)
        self.assertEqual(len(min_outputs), 4)
        # All min_outputs should be positive
        for m in min_outputs:
            self.assertGreater(m, 0)

    def test_format_report(self):
        """Slippage report should contain all symbols."""
        estimates = estimate_rebalance_slippage(
            self.allocation,
            self.weights,
            portfolio_value_usd=50_000,
        )
        report = format_slippage_report(estimates)
        self.assertIn("SUI", report)
        self.assertIn("BTC", report)
        self.assertIn("Almgren-Chriss", report)


class TestEdgeCases(unittest.TestCase):
    """Edge cases and error handling."""

    def test_zero_order_size(self):
        """Zero order should have zero impact."""
        est = estimate_market_impact("BTC", order_size_usd=0)
        self.assertEqual(est.raw_impact_pct, 0)

    def test_empty_allocation(self):
        """Empty allocation produces empty estimates."""
        estimates = estimate_rebalance_slippage({}, {}, portfolio_value_usd=50_000)
        self.assertEqual(len(estimates), 0)

    def test_very_large_portfolio(self):
        """$50M portfolio should show significant impact on SUI."""
        allocation = {"SUI": 1}
        weights = {"SUI": 1.0}
        estimates = estimate_rebalance_slippage(
            allocation,
            weights,
            portfolio_value_usd=50_000_000,
        )
        # 50M / 400M volume = 12.5% of ADV → substantial impact
        self.assertGreater(estimates["SUI"].raw_impact_pct, 0.01)


if __name__ == "__main__":
    unittest.main()
