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
        return self._call("sui_getObject", [
            object_id,
            {"showContent": True, "showType": True, "showOwner": True}
        ])

    def get_events(self, tx_digest: str) -> List[Dict]:
        """Get events emitted by a transaction."""
        return self._call("sui_getEvents", [tx_digest])

    def query_events(self, event_type: str, limit: int = 50) -> List[Dict]:
        """Query events by Move event type."""
        result = self._call("suix_queryEvents", [
            {"MoveEventType": event_type},
            None,
            limit,
            False,
        ])
        return result.get("data", [])

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
            "sui", "client", "call",
            "--package", PACKAGE_ID,
            "--module", "portfolio",
            "--function", "execute_trade",
            "--args",
            PORTFOLIO_OBJECT_ID,
            json.dumps(symbols),
            json.dumps(alloc_bits),
            json.dumps(weight_bps),
            str(int(expected_return * 10000)),
            str(int(expected_risk * 10000)),
            f'"{reason}"',
            "--gas-budget", "10000000",
            "--json",
        ]

        logger.info(f"Submitting on-chain trade: {' '.join(cmd)}")

        t0 = time.time()
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            elapsed = time.time() - t0

            if result.returncode == 0:
                tx_data = json.loads(result.stdout)
                digest = tx_data.get("digest", "")
                gas = tx_data.get("effects", {}).get("gasUsed", {})
                gas_total = int(gas.get("computationCost", 0)) + int(gas.get("storageCost", 0))
                events = tx_data.get("events", [])

                logger.info(f"✅ Trade executed on-chain: {digest} ({elapsed:.2f}s)")
                return TxResult(
                    success=True,
                    digest=digest,
                    gas_used=gas_total,
                    events=events,
                    timestamp=t0,
                )
            else:
                logger.error(f"❌ Transaction failed: {result.stderr}")
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
        fake_digest = hashlib.sha256(
            json.dumps(allocation, sort_keys=True).encode()
        ).hexdigest()[:44]

        logger.info(f"🔸 DRY-RUN: would submit trade {fake_digest}")
        return TxResult(
            success=True,
            digest=f"DRY_RUN_{fake_digest}",
            gas_used=0,
            events=[{
                "type": "dry_run::TradeExecuted",
                "allocation": allocation,
                "weights": weights,
                "reason": reason,
            }],
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
