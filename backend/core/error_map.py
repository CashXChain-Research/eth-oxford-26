#!/usr/bin/env python3
"""
error_map.py — Graceful Failure Layer

Maps Move abort codes to frontend-friendly messages.
Catches Sui transaction aborts and translates them.

Usage:
    from core.error_map import parse_abort_error, error_response_body, log_error, ERROR_MAP
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  ERROR CODE REGISTRY
# ═══════════════════════════════════════════════════════════


@dataclass
class MoveError:
    code: int
    constant: str
    module: str
    severity: str  # 'warning' | 'error' | 'critical'
    frontend_message: str
    dev_message: str
    recovery: str


ERROR_MAP: Dict[int, MoveError] = {
    0: MoveError(
        code=0,
        constant="EInvalidAgent",
        module="portfolio",
        severity="critical",
        frontend_message="Security error: agent not authorized.",
        dev_message="AgentCap.portfolio_id does not match the target Portfolio object ID.",
        recovery="Verify AGENT_CAP_ID in .env is bound to the correct PORTFOLIO_ID. Re-issue via issue_agent_cap if needed.",
    ),
    1: MoveError(
        code=1,
        constant="EAgentFrozen",
        module="portfolio",
        severity="critical",
        frontend_message="Agent frozen: admin has blocked this agent.",
        dev_message="Agent address is in the frozen_agents vector. Admin must call unfreeze_agent.",
        recovery="Ask Korbinian to run: sui client call --function unfreeze_agent --args <admin_cap> <portfolio> <agent_addr>",
    ),
    2: MoveError(
        code=2,
        constant="ECooldownActive",
        module="portfolio",
        severity="warning",
        frontend_message="Quantum cooldown: please wait 60 seconds.",
        dev_message="Last trade was less than cooldown_ms ago. Current default: 60s.",
        recovery="Wait for the cooldown to expire, or ask admin to lower cooldown via update_limits.",
    ),
    3: MoveError(
        code=3,
        constant="EVolumeExceeded",
        module="portfolio",
        severity="error",
        frontend_message="Risk limit exceeded: daily volume exhausted.",
        dev_message="total_traded_today + amount > daily_volume_limit. Default: 50 SUI/day.",
        recovery="Wait for the 24h rolling window to reset, or ask admin to raise daily_volume_limit.",
    ),
    4: MoveError(
        code=4,
        constant="EDrawdownExceeded",
        module="portfolio",
        severity="error",
        frontend_message="Drawdown protection: trade would exceed maximum loss.",
        dev_message="Projected balance after trade would exceed max_drawdown_bps from peak. Default: 10%.",
        recovery="Reduce trade amount, or ask admin to raise max_drawdown_bps.",
    ),
    5: MoveError(
        code=5,
        constant="EInsufficientBalance",
        module="portfolio",
        severity="error",
        frontend_message="Insufficient portfolio balance.",
        dev_message="Portfolio balance < requested trade amount.",
        recovery="Deposit more SUI via admin deposit, or reduce trade amount.",
    ),
    6: MoveError(
        code=6,
        constant="EPaused",
        module="portfolio",
        severity="critical",
        frontend_message="Portfolio paused: all trades are blocked.",
        dev_message="Portfolio.paused == true. Admin activated the kill switch.",
        recovery='Ask Korbinian to resume: POST /api/pause { "paused": false }',
    ),
    7: MoveError(
        code=7,
        constant="ESlippageExceeded",
        module="portfolio",
        severity="warning",
        frontend_message="Slippage too high: minimum output not reached.",
        dev_message="output_amount < min_output. The DEX (or mock) returned less than expected.",
        recovery="Increase slippage tolerance (lower min_output) or wait for better market conditions.",
    ),
    8: MoveError(
        code=8,
        constant="EAtomicRebalanceFailed",
        module="portfolio",
        severity="error",
        frontend_message="Atomic rebalance failed: total value check failed.",
        dev_message="Post-rebalance portfolio value check failed. The combined swaps would violate safety bounds.",
        recovery="Reduce swap amounts or split into smaller rebalances.",
    ),
    9: MoveError(
        code=9,
        constant="ESwapCountMismatch",
        module="portfolio",
        severity="error",
        frontend_message="Invalid swap configuration: lengths do not match.",
        dev_message="swap_amounts.length != swap_min_outputs.length. Arrays must match.",
        recovery="Ensure swap_amounts and swap_min_outputs arrays have the same length.",
    ),
    10: MoveError(
        code=10,
        constant="EPostRebalanceDrawdown",
        module="portfolio",
        severity="critical",
        frontend_message="Security limit: portfolio value after rebalance too low.",
        dev_message="Post-rebalance drawdown exceeds max_drawdown_bps from peak. Entire PTB is reverted.",
        recovery="Reduce total swap amounts. The combined effect exceeds the drawdown limit.",
    ),
    11: MoveError(
        code=11,
        constant="EProtocolNotWhitelisted",
        module="portfolio",
        severity="critical",
        frontend_message="Protocol not whitelisted: target address not in whitelist.",
        dev_message="Target protocol address is not in the portfolio's protocol_whitelist vector.",
        recovery="Ask admin to add the protocol via add_to_whitelist, or use a whitelisted protocol.",
    ),
    # Oracle module errors (100+)
    100: MoveError(
        code=100,
        constant="ESlippageTooHigh",
        module="oracle",
        severity="error",
        frontend_message="Oracle slippage: price deviation too high (>1%).",
        dev_message="Oracle price vs expected price deviation exceeds max_slippage_bps. Default: 100 bps (1%).",
        recovery="Wait for price to stabilize or increase max_slippage_bps via update_oracle_config.",
    ),
    101: MoveError(
        code=101,
        constant="EPriceStale",
        module="oracle",
        severity="error",
        frontend_message="Oracle price stale: price feed too old.",
        dev_message="Oracle price timestamp is older than max_staleness_ms. Default: 30s.",
        recovery="Refresh the Pyth price feed before calling the swap, or increase max_staleness_ms.",
    ),
    102: MoveError(
        code=102,
        constant="EPriceNegative",
        module="oracle",
        severity="critical",
        frontend_message="Invalid oracle price: price is zero or negative.",
        dev_message="oracle_price_x8 or expected_price_x8 is zero. Check Pyth feed health.",
        recovery="Verify the Pyth price feed is returning valid data.",
    ),
    103: MoveError(
        code=103,
        constant="EInvalidOracleConfig",
        module="oracle",
        severity="error",
        frontend_message="Invalid oracle configuration.",
        dev_message="OracleConfig parameter out of range (max_slippage_bps > 1000 or max_staleness_ms < 1000).",
        recovery="Use valid config: slippage ≤ 1000 bps (10%), staleness ≥ 1000ms.",
    ),
}


# ═══════════════════════════════════════════════════════════
#  PARSER — extracts abort code from Sui error messages
# ═══════════════════════════════════════════════════════════


@dataclass
class ParsedError:
    is_move_abort: bool
    code: Optional[int]
    mapped: Optional[MoveError]
    frontend_message: str
    raw_error: str


# Regex patterns to extract abort codes from Sui errors
_ABORT_PATTERNS = [
    re.compile(r"MoveAbort\([^)]*,\s*(\d+)\)", re.IGNORECASE),
    re.compile(r"abort[_ ]code[:\s]+(\d+)", re.IGNORECASE),
    re.compile(r"Move abort (\d+)", re.IGNORECASE),
    re.compile(r"status_code.*?(\d+)", re.IGNORECASE),
    re.compile(r"VMError.*?(\d+)", re.IGNORECASE),
]


def parse_abort_error(error: Any) -> ParsedError:
    """
    Parse a Sui transaction error and return a structured,
    frontend-friendly result.

    Handles patterns like:
      - "MoveAbort(_, 2)"
      - "abort_code: 6"
      - "status: { error: '...abort...2...' }"
    """
    raw = str(error)

    for pat in _ABORT_PATTERNS:
        match = pat.search(raw)
        if match:
            code = int(match.group(1))
            mapped = ERROR_MAP.get(code)
            return ParsedError(
                is_move_abort=True,
                code=code,
                mapped=mapped,
                frontend_message=(mapped.frontend_message if mapped else f" Unknown error (code {code})"),
                raw_error=raw,
            )

    # Not a Move abort
    return ParsedError(
        is_move_abort=False,
        code=None,
        mapped=None,
        frontend_message=f"Unexpected error: {raw[:200]}",
        raw_error=raw,
    )


# ═══════════════════════════════════════════════════════════
#  HELPERS FOR RELAYER
# ═══════════════════════════════════════════════════════════


def error_response_body(error: Any) -> dict:
    """Full error response body for the relayer to send to clients."""
    parsed = parse_abort_error(error)
    return {
        "success": False,
        "error": {
            "isMoveAbort": parsed.is_move_abort,
            "code": parsed.code,
            "constant": parsed.mapped.constant if parsed.mapped else None,
            "severity": parsed.mapped.severity if parsed.mapped else "error",
            "message": parsed.frontend_message,
            "recovery": parsed.mapped.recovery if parsed.mapped else None,
            "raw": parsed.raw_error,
        },
    }


def log_error(context: str, error: Any) -> None:
    """Console-friendly log line."""
    parsed = parse_abort_error(error)
    if parsed.is_move_abort and parsed.mapped:
        logger.error(
            f"[{context}] {parsed.mapped.constant} (code {parsed.code}): {parsed.mapped.dev_message}"
        )
    else:
        logger.error(f"[{context}] {parsed.raw_error}")