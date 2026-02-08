#!/usr/bin/env python3
"""
On-Chain Liquidity Monitor — Sui DEX (Cetus Protocol).

Queries Cetus pool objects via Sui JSON-RPC to determine real-time
liquidity depth. The Risk Agent uses this to dynamically adjust
concentration limits:

  - Deep liquidity (>$1M)  → standard 40% max position
  - Medium liquidity        → reduced 30% max
  - Thin liquidity (<$100K) → conservative 20% max

This is NOT a glorified API call. The data comes directly from the
blockchain state (Cetus Pool objects on Sui), parsed from Move struct
fields — the same source of truth the DEX smart contract uses.

Cetus Pool structure (Move):
  struct Pool<phantom CoinTypeA, phantom CoinTypeB> {
      coin_a: Balance<CoinTypeA>,
      coin_b: Balance<CoinTypeB>,
      current_sqrt_price: u128,
      current_tick_index: I32,
      liquidity: u128,
      ...
  }

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ── Sui RPC config ───────────────────────────────────
SUI_RPC_URL = os.getenv("SUI_RPC_URL", "https://fullnode.mainnet.sui.io:443")

# ── Known Cetus pool objects on Sui mainnet ──────────
# These are the main SUI/USDC and major token pools on Cetus DEX.
# Pool object IDs are stable on-chain identifiers.
CETUS_POOLS: Dict[str, str] = {
    "SUI/USDC": os.getenv(
        "CETUS_POOL_SUI_USDC",
        "0xcf994611fd4c48e277ce3ffd4d4364c914af2c3cbb05f7bf6facd371de688571",
    ),
    "SUI/USDT": os.getenv(
        "CETUS_POOL_SUI_USDT",
        "0x06d8af9e6afd27262db436f0d37b304a041f710c3ea1fa4c3a9bab36b3569ad3",
    ),
    # Extend with more pools as needed
}

# ── Liquidity thresholds (USD-equivalent) ────────────
LIQUIDITY_DEEP = 1_000_000  # >$1M = deep
LIQUIDITY_MEDIUM = 100_000  # $100K-$1M = medium
# Below $100K = thin

# ── Position limits by liquidity tier ────────────────
POSITION_LIMITS = {
    "deep": 0.40,  # standard 40%
    "medium": 0.30,  # reduced 30%
    "thin": 0.20,  # conservative 20%
    "unknown": 0.25,  # RPC failed, be cautious
}

# ── Cache ────────────────────────────────────────────
_liquidity_cache: Dict[str, dict] = {}
_cache_ts: float = 0.0
CACHE_TTL_S = 30.0  # refresh every 30s


@dataclass
class PoolLiquidity:
    """Liquidity state for a single DEX pool."""

    pool_name: str
    pool_id: str
    # Raw on-chain values
    liquidity_raw: int = 0  # u128 liquidity from Pool struct
    coin_a_balance: int = 0  # Balance<CoinA> (in base units)
    coin_b_balance: int = 0  # Balance<CoinB> (in base units)
    sqrt_price: int = 0  # current_sqrt_price
    tick_index: int = 0  # current_tick_index
    # Derived
    tvl_estimate_usd: float = 0.0
    tier: str = "unknown"  # "deep", "medium", "thin", "unknown"
    timestamp: float = 0.0
    source: str = "rpc"  # "rpc" or "fallback"


def _sui_rpc_call(method: str, params: list) -> dict:
    """Low-level Sui JSON-RPC call."""
    if not HAS_HTTPX:
        raise RuntimeError("httpx not installed")

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }
    with httpx.Client(timeout=10) as client:
        resp = client.post(SUI_RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()

    if "error" in data:
        raise RuntimeError(f"Sui RPC error: {data['error']}")
    return data.get("result", {})


def fetch_pool_liquidity(pool_name: str, pool_id: str) -> PoolLiquidity:
    """
    Fetch real-time liquidity from a Cetus pool via Sui RPC.

    Reads the Pool object's fields: liquidity, coin_a balance, coin_b balance,
    current_sqrt_price, and tick_index.
    """
    result = PoolLiquidity(
        pool_name=pool_name,
        pool_id=pool_id,
        timestamp=time.time(),
    )

    try:
        obj = _sui_rpc_call(
            "sui_getObject",
            [pool_id, {"showContent": True, "showType": True}],
        )

        content = obj.get("data", {}).get("content", {})
        fields = content.get("fields", {})

        if not fields:
            logger.warning(f"[{pool_name}] No fields in pool object {pool_id[:16]}…")
            result.source = "fallback"
            return result

        # Parse Cetus Pool struct fields
        result.liquidity_raw = int(fields.get("liquidity", 0))
        result.sqrt_price = int(fields.get("current_sqrt_price", 0))
        result.tick_index = int(fields.get("current_tick_index", {}).get("bits", 0))

        # Coin balances (nested in Balance struct)
        coin_a = fields.get("coin_a", {})
        coin_b = fields.get("coin_b", {})
        if isinstance(coin_a, dict):
            result.coin_a_balance = int(coin_a.get("fields", {}).get("balance", coin_a.get("balance", 0)))
        if isinstance(coin_b, dict):
            result.coin_b_balance = int(coin_b.get("fields", {}).get("balance", coin_b.get("balance", 0)))

        # Estimate TVL in USD
        # SUI pools: coin_b is typically USDC (6 decimals)
        # coin_a is SUI (9 decimals)
        usdc_amount = result.coin_b_balance / 1e6  # USDC has 6 decimals
        sui_amount = result.coin_a_balance / 1e9  # SUI has 9 decimals

        # Rough SUI price estimate from sqrt_price (Cetus uses Q64.64 format)
        if result.sqrt_price > 0:
            # price = (sqrt_price / 2^64)^2, adjusted for decimal difference
            price_ratio = (result.sqrt_price / (2 ** 64)) ** 2
            # Adjust for SUI(9 dec) vs USDC(6 dec): multiply by 10^(9-6) = 1000
            sui_price_usd = price_ratio * 1000 if price_ratio > 0 else 1.0
        else:
            sui_price_usd = 1.0

        result.tvl_estimate_usd = usdc_amount + (sui_amount * sui_price_usd)
        result.source = "rpc"

        # Classify liquidity tier
        if result.tvl_estimate_usd >= LIQUIDITY_DEEP:
            result.tier = "deep"
        elif result.tvl_estimate_usd >= LIQUIDITY_MEDIUM:
            result.tier = "medium"
        else:
            result.tier = "thin"

        logger.info(
            f"[{pool_name}] TVL≈${result.tvl_estimate_usd:,.0f} "
            f"tier={result.tier} liquidity={result.liquidity_raw} "
            f"coinA={sui_amount:.0f} SUI coinB={usdc_amount:.0f} USDC"
        )

    except Exception as e:
        logger.warning(f"[{pool_name}] RPC failed ({e}), using fallback tier")
        result.source = "fallback"
        result.tier = "unknown"

    return result


def get_dynamic_position_limit(pool_name: str = "SUI/USDC") -> float:
    """
    Get the current max position weight based on on-chain liquidity.

    Returns a float between 0.20 and 0.40.
    """
    pool_id = CETUS_POOLS.get(pool_name)
    if not pool_id:
        logger.warning(f"No pool ID configured for {pool_name}")
        return POSITION_LIMITS["unknown"]

    # Check cache
    global _liquidity_cache, _cache_ts
    now = time.time()
    if pool_name in _liquidity_cache and (now - _cache_ts) < CACHE_TTL_S:
        cached = _liquidity_cache[pool_name]
        return POSITION_LIMITS.get(cached["tier"], POSITION_LIMITS["unknown"])

    # Fetch fresh
    try:
        pool = fetch_pool_liquidity(pool_name, pool_id)
        _liquidity_cache[pool_name] = {
            "tier": pool.tier,
            "tvl_usd": pool.tvl_estimate_usd,
            "timestamp": pool.timestamp,
            "source": pool.source,
        }
        _cache_ts = now
        return POSITION_LIMITS.get(pool.tier, POSITION_LIMITS["unknown"])
    except Exception as e:
        logger.warning(f"Liquidity check failed: {e}")
        return POSITION_LIMITS["unknown"]


def get_all_pool_liquidity() -> Dict[str, PoolLiquidity]:
    """Fetch liquidity for all configured Cetus pools."""
    results = {}
    for name, pool_id in CETUS_POOLS.items():
        results[name] = fetch_pool_liquidity(name, pool_id)
    return results


def get_liquidity_summary() -> Dict:
    """
    Return a summary dict suitable for API responses / frontend display.
    """
    pools = get_all_pool_liquidity()
    summary = {
        "timestamp": time.time(),
        "pools": {},
        "overall_tier": "unknown",
    }

    tiers = []
    for name, pool in pools.items():
        summary["pools"][name] = {
            "tvl_usd": pool.tvl_estimate_usd,
            "tier": pool.tier,
            "position_limit": POSITION_LIMITS.get(pool.tier, POSITION_LIMITS["unknown"]),
            "liquidity_raw": pool.liquidity_raw,
            "source": pool.source,
        }
        tiers.append(pool.tier)

    # Overall tier = worst tier across all pools
    tier_rank = {"thin": 0, "unknown": 1, "medium": 2, "deep": 3}
    if tiers:
        worst = min(tiers, key=lambda t: tier_rank.get(t, 1))
        summary["overall_tier"] = worst

    return summary


# ── CLI test ─────────────────────────────────────────


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    print("\n── On-Chain Liquidity Check (Cetus DEX) ──")

    for pool_name, pool_id in CETUS_POOLS.items():
        print(f"\n  Pool: {pool_name}")
        print(f"  Object: {pool_id[:20]}…")
        try:
            pool = fetch_pool_liquidity(pool_name, pool_id)
            print(f"  TVL:    ${pool.tvl_estimate_usd:,.0f}")
            print(f"  Tier:   {pool.tier}")
            print(f"  Limit:  {POSITION_LIMITS[pool.tier]:.0%} max position")
            print(f"  Source: {pool.source}")
            if pool.liquidity_raw > 0:
                print(f"  Raw Liq: {pool.liquidity_raw:,}")
                print(f"  CoinA:   {pool.coin_a_balance:,} (base units)")
                print(f"  CoinB:   {pool.coin_b_balance:,} (base units)")
        except Exception as e:
            print(f"  Error: {e}")

    limit = get_dynamic_position_limit()
    print(f"\n  Dynamic position limit: {limit:.0%}")


if __name__ == "__main__":
    main()
