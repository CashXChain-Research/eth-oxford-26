#!/usr/bin/env python3
"""
Sui blockchain client for portfolio trade execution.

Handles:
  - Building move_call transactions for the PortfolioState contract
  - Signing with the execution agent's private key
  - Submitting and waiting for on-chain confirmation
  - Reading portfolio state & audit logs

Uses httpx for JSON-RPC (no pysui dependency required, but supports it).

Author: Valentin Israel — ETH Oxford Hackathon 2026
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:
    raise ImportError("pip install httpx")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SUI_RPC_URL = os.getenv("SUI_RPC_URL", "https://fullnode.devnet.sui.io:443")
PACKAGE_ID = os.getenv("PACKAGE_ID", "")
PORTFOLIO_OBJECT_ID = os.getenv("PORTFOLIO_OBJECT_ID", "")
SUI_PRIVATE_KEY = os.getenv("SUI_PRIVATE_KEY", "")

# Oracle config for slippage protection
ORACLE_CONFIG_ID = os.getenv("ORACLE_CONFIG_ID", "")
PYTH_PRICE_FEED_ID = os.getenv("PYTH_PRICE_FEED_ID", "")  # For mainnet/testnet
MAX_SLIPPAGE_BPS = int(os.getenv("MAX_SLIPPAGE_BPS", "100"))  # 100 bps = 1% default

# Portfolio state cache (for reconciliation)
_portfolio_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: float = 0.0
CACHE_TTL_S = 5.0  # Refresh cache if > 5s old


@dataclass
class TxResult:
    """Result of an on-chain transaction."""

    success: bool
    digest: str = ""
    gas_used: int = 0
    events: List[Dict] = None
    error: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if self.events is None:
            self.events = []


# ---------------------------------------------------------------------------
# Low-level RPC helper
# ---------------------------------------------------------------------------


class SuiClient:
    """Minimal Sui JSON-RPC client."""

    def __init__(self, rpc_url: str = SUI_RPC_URL):
        self.rpc_url = rpc_url
        self._req_id = 0

    def _call(self, method: str, params: list) -> Dict[str, Any]:
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(self.rpc_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result", {})

    # ----- Read operations -----

    def get_object(self, object_id: str) -> Dict[str, Any]:
        """Fetch on-chain object by ID."""
        return self._call(
            "sui_getObject", [object_id, {"showContent": True, "showType": True, "showOwner": True}]
        )

    def get_events(self, tx_digest: str) -> List[Dict]:
        """Get events emitted by a transaction."""
        return self._call("sui_getEvents", [tx_digest])

    def query_events(self, event_type: str, limit: int = 50) -> List[Dict]:
        """Query events by Move event type."""
        result = self._call(
            "suix_queryEvents",
            [
                {"MoveEventType": event_type},
                None,
                limit,
                False,
            ],
        )
        return result.get("data", [])

    # ----- Portfolio State Reconciliation -----

    def refresh_portfolio_state(self, object_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Read the latest Portfolio state from the blockchain.
        Invalidates cache and updates _portfolio_cache.
        
        Call this AFTER a successful trade to avoid stale state.
        """
        global _portfolio_cache, _cache_timestamp
        oid = object_id or PORTFOLIO_OBJECT_ID
        if not oid:
            raise ValueError("No PORTFOLIO_OBJECT_ID configured")
        
        portfolio_obj = self.get_object(oid)
        fields = portfolio_obj.get("data", {}).get("content", {}).get("fields", {})
        
        _portfolio_cache = {
            "id": oid,
            "balance": fields.get("balance", "0"),
            "peak_balance": fields.get("peak_balance", 0),
            "trade_count": fields.get("trade_count", 0),
            "paused": fields.get("paused", False),
            "total_traded_today": fields.get("total_traded_today", 0),
            "max_drawdown_bps": fields.get("max_drawdown_bps", 0),
            "daily_volume_limit": fields.get("daily_volume_limit", 0),
            "cooldown_ms": fields.get("cooldown_ms", 0),
            "timestamp": time.time(),
        }
        _cache_timestamp = time.time()
        logger.info(f" Portfolio state synced: balance={fields.get('balance')}, trades={fields.get('trade_count')}")
        return _portfolio_cache

    def get_cached_portfolio_state(self, refresh_if_stale: bool = True) -> Optional[Dict[str, Any]]:
        """
        Return cached portfolio state. If refresh_if_stale=True and cache is >TTL old,
        fetch fresh from RPC.
        
        Use this to avoid excessive RPC calls between trades.
        """
        global _portfolio_cache, _cache_timestamp
        
        if _portfolio_cache is None:
            if refresh_if_stale:
                return self.refresh_portfolio_state()
            return None
        
        age_s = time.time() - _cache_timestamp
        if refresh_if_stale and age_s > CACHE_TTL_S:
            return self.refresh_portfolio_state()
        
        return _portfolio_cache

    # ----- Oracle Price Sync (Slippage Protection) -----

    def calculate_min_output(
        self,
        amount: float,
        expected_price: float,
        slippage_tolerance_bps: Optional[int] = None,
    ) -> int:
        """
        Given an expected off-chain price, calculate min_output with slippage protection.
        
        min_output = amount * (expected_price * (1 - slippage_bps / 10000))
        
        Args:
            amount: Input amount (e.g., SUI to swap)
            expected_price: Expected price from off-chain oracle (e.g., CoinGecko)
            slippage_tolerance_bps: Max acceptable slippage in BPS (default: MAX_SLIPPAGE_BPS)
        
        Returns:
            min_output: Minimum output amount for on-chain validation
        """
        slippage_bps = slippage_tolerance_bps or MAX_SLIPPAGE_BPS
        slippage_factor = 1.0 - (slippage_bps / 10_000)
        min_output_float = amount * expected_price * slippage_factor
        min_output = int(min_output_float)
        logger.info(
            f"Min-output calculation: {amount} * {expected_price:.4f} * {slippage_factor:.4f} = {min_output} "
            f"(slippage tolerance: {slippage_bps} bps)"
        )
        return min_output

    # ----- Portfolio-specific reads -----

    def get_portfolio_state(self) -> Dict[str, Any]:
        """Read the PortfolioState shared object."""
        if not PORTFOLIO_OBJECT_ID:
            logger.warning("PORTFOLIO_OBJECT_ID not set")
            return {}
        obj = self.get_object(PORTFOLIO_OBJECT_ID)
        content = obj.get("data", {}).get("content", {})
        return content.get("fields", {})

    def get_audit_trail(self, limit: int = 20) -> List[Dict]:
        """Fetch recent AuditLog events from the contract."""
        if not PACKAGE_ID:
            return []
        event_type = f"{PACKAGE_ID}::portfolio::TradeExecuted"
        return self.query_events(event_type, limit)


# ---------------------------------------------------------------------------
# Transaction builder (via Sui CLI for hackathon speed)
# ---------------------------------------------------------------------------


class SuiTransactor:
    """
    Build and submit portfolio transactions.

    For the hackathon we shell out to `sui client call`.
    In production, use pysui or the Sui TypeScript SDK.
    """

    def __init__(self, rpc_url: str = SUI_RPC_URL):
        self.client = SuiClient(rpc_url)

    @staticmethod
    def get_explorer_url(digest: str, network: str = "devnet") -> str:
        """Generate Sui explorer URL for a transaction digest."""
        base = f"https://suiscan.xyz/{network}"
        return f"{base}/tx/{digest}"

    def execute_rebalance(
        self,
        allocation: Dict[str, int],
        weights: Dict[str, float],
        expected_return: float,
        expected_risk: float,
        reason: str = "QUBO optimization",
    ) -> TxResult:
        """
        Call the on-chain execute_trade function.

        Maps the QUBO result to Sui move_call args.
        """
        if not PACKAGE_ID or not PORTFOLIO_OBJECT_ID:
            logger.error("PACKAGE_ID or PORTFOLIO_OBJECT_ID not configured")
            return TxResult(success=False, error="Missing contract config")

        # Encode allocation as vectors for Move
        symbols = list(allocation.keys())
        alloc_bits = [str(allocation[s]) for s in symbols]
        weight_bps = [str(int(weights.get(s, 0) * 10000)) for s in symbols]  # basis points

        # Build the Sui CLI command
        import subprocess

        cmd = [
            "sui",
            "client",
            "call",
            "--package",
            PACKAGE_ID,
            "--module",
            "portfolio",
            "--function",
            "execute_trade",
            "--args",
            PORTFOLIO_OBJECT_ID,
            json.dumps(symbols),
            json.dumps(alloc_bits),
            json.dumps(weight_bps),
            str(int(expected_return * 10000)),
            str(int(expected_risk * 10000)),
            f'"{reason}"',
            "--gas-budget",
            "10000000",
            "--json",
        ]

        logger.info(f"Submitting on-chain trade: {' '.join(cmd)}")

        t0 = time.time()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            elapsed = time.time() - t0

            if result.returncode == 0:
                tx_data = json.loads(result.stdout)
                digest = tx_data.get("digest", "")
                gas = tx_data.get("effects", {}).get("gasUsed", {})
                gas_total = int(gas.get("computationCost", 0)) + int(gas.get("storageCost", 0))
                events = tx_data.get("events", [])

                logger.info(f" Trade executed on-chain: {digest} ({elapsed:.2f}s)")
                
                # ── STATE RECONCILIATION [NEW] ──
                # Immediately refresh portfolio state to avoid stale state bugs
                try:
                    self.client.refresh_portfolio_state()
                    logger.info(" Portfolio state synced after trade")
                except Exception as e:
                    logger.warning(f"  State sync failed: {e} (continuing)")
                
                return TxResult(
                    success=True,
                    digest=digest,
                    gas_used=gas_total,
                    events=events,
                    timestamp=t0,
                )
            else:
                logger.error(f" Transaction failed: {result.stderr}")
                return TxResult(success=False, error=result.stderr.strip())

        except subprocess.TimeoutExpired:
            return TxResult(success=False, error="Transaction timed out")
        except FileNotFoundError:
            logger.warning("sui CLI not found — running in dry-run mode")
            return self._dry_run(allocation, weights, reason)
        except Exception as e:
            return TxResult(success=False, error=str(e))

    def _dry_run(
        self,
        allocation: Dict[str, int],
        weights: Dict[str, float],
        reason: str,
    ) -> TxResult:
        """Simulate a transaction when sui CLI is not available."""
        import hashlib

        fake_digest = hashlib.sha256(json.dumps(allocation, sort_keys=True).encode()).hexdigest()[
            :44
        ]

        logger.info(f" DRY-RUN: would submit trade {fake_digest}")
        return TxResult(
            success=True,
            digest=f"DRY_RUN_{fake_digest}",
            gas_used=0,
            events=[
                {
                    "type": "dry_run::TradeExecuted",
                    "allocation": allocation,
                    "weights": weights,
                    "reason": reason,
                }
            ],
            timestamp=time.time(),
        )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def get_portfolio_status() -> Dict[str, Any]:
    """Return current portfolio state for the frontend."""
    client = SuiClient()
    state = client.get_portfolio_state()
    trail = client.get_audit_trail()
    return {
        "portfolio": state,
        "recent_trades": trail,
        "timestamp": time.time(),
    }
