#!/usr/bin/env python3
"""
ptb_builder.py — Programmable Transaction Block (PTB) builder

Builds Sui CLI commands for each portfolio transaction type.
Each function returns a list of args for subprocess.run(["sui", "client", "call", ...]).

For hackathon speed, we shell out to `sui client call`.
In production, migrate to pysui SDK.

Usage:
    from blockchain.ptb_builder import build_swap_and_rebalance, build_set_paused
    import subprocess, json
    cmd = build_swap_and_rebalance(amount_mist=1_000_000_000, min_output=950_000_000)
    result = subprocess.run(cmd, capture_output=True, text=True)
    tx_data = json.loads(result.stdout)
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  ON-CHAIN IDS — filled after deploy.sh
# ═══════════════════════════════════════════════════════════

PKG = os.getenv("PACKAGE_ID", "")
PORTFOLIO_ID = os.getenv("PORTFOLIO_ID", os.getenv("PORTFOLIO_OBJECT_ID", ""))
AGENT_CAP_ID = os.getenv("AGENT_CAP_ID", "")
ADMIN_CAP_ID = os.getenv("ADMIN_CAP_ID", "")
ORACLE_CONFIG_ID = os.getenv("ORACLE_CONFIG_ID", "")
SUI_CLOCK = "0x6"
GAS_BUDGET = os.getenv("GAS_BUDGET", "10000000")


# ═══════════════════════════════════════════════════════════
#  RESULT TYPE
# ═══════════════════════════════════════════════════════════


@dataclass
class TxResult:
    """Result of a Sui transaction."""

    success: bool
    digest: str = ""
    gas_used: int = 0
    events: List[Dict] = field(default_factory=list)
    error: str = ""
    status: str = ""


def _run_sui_cmd(cmd: List[str]) -> TxResult:
    """Execute a sui CLI command and parse the JSON result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            tx_data = json.loads(result.stdout)
            digest = tx_data.get("digest", "")
            effects = tx_data.get("effects", {})
            gas = effects.get("gasUsed", {})
            gas_total = int(gas.get("computationCost", 0)) + int(gas.get("storageCost", 0))
            status = effects.get("status", {}).get("status", "unknown")
            events = tx_data.get("events", [])

            formatted_events = [
                {"type": ev.get("type", ""), "data": ev.get("parsedJson", {})} for ev in events
            ]

            return TxResult(
                success=status == "success",
                digest=digest,
                gas_used=gas_total,
                events=formatted_events,
                status=status,
                error=effects.get("status", {}).get("error", "") if status != "success" else "",
            )
        else:
            return TxResult(success=False, error=result.stderr.strip())

    except subprocess.TimeoutExpired:
        return TxResult(success=False, error="Transaction timed out (30s)")
    except FileNotFoundError:
        return TxResult(success=False, error="sui CLI not found — install from https://docs.sui.io")
    except json.JSONDecodeError as e:
        return TxResult(success=False, error=f"Failed to parse sui output: {e}")
    except Exception as e:
        return TxResult(success=False, error=str(e))


def _base_cmd(module: str, function: str) -> List[str]:
    """Build the base sui client call command."""
    return [
        "sui",
        "client",
        "call",
        "--package",
        PKG,
        "--module",
        module,
        "--function",
        function,
        "--gas-budget",
        GAS_BUDGET,
        "--json",
    ]


# ═══════════════════════════════════════════════════════════
#  1. swap_and_rebalance (atomic demo / same-module swap)
# ═══════════════════════════════════════════════════════════


def build_swap_and_rebalance(
    amount_mist: int,
    min_output: int,
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> List[str]:
    """Build CLI args for swap_and_rebalance."""
    cmd = _base_cmd("portfolio", "swap_and_rebalance")
    cmd += [
        "--args",
        AGENT_CAP_ID,
        PORTFOLIO_ID,
        str(amount_mist),
        str(min_output),
        str(is_quantum_optimized).lower(),
        str(quantum_optimization_score),
        SUI_CLOCK,
    ]
    return cmd


def execute_swap_and_rebalance(
    amount_mist: int,
    min_output: int,
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> TxResult:
    """Build and execute swap_and_rebalance in one step."""
    cmd = build_swap_and_rebalance(
        amount_mist,
        min_output,
        is_quantum_optimized,
        quantum_optimization_score,
    )
    result = _run_sui_cmd(cmd)
    if result.success:
        logger.info(f" swap_and_rebalance TX: {result.digest}")
    else:
        logger.error(f" swap_and_rebalance failed: {result.error}")
    return result


# ═══════════════════════════════════════════════════════════
#  2. execute_rebalance (demo / dry-run — no fund movement)
# ═══════════════════════════════════════════════════════════


def build_execute_rebalance(
    amount_mist: int,
    is_quantum_optimized: bool = True,
) -> List[str]:
    """Build CLI args for execute_rebalance."""
    cmd = _base_cmd("portfolio", "execute_rebalance")
    cmd += [
        "--args",
        AGENT_CAP_ID,
        PORTFOLIO_ID,
        str(amount_mist),
        str(is_quantum_optimized).lower(),
        SUI_CLOCK,
    ]
    return cmd


def execute_rebalance(
    amount_mist: int,
    is_quantum_optimized: bool = True,
) -> TxResult:
    """Build and execute execute_rebalance."""
    cmd = build_execute_rebalance(amount_mist, is_quantum_optimized)
    result = _run_sui_cmd(cmd)
    if result.success:
        logger.info(f" execute_rebalance TX: {result.digest}")
    else:
        logger.error(f" execute_rebalance failed: {result.error}")
    return result


# ═══════════════════════════════════════════════════════════
#  3. set_paused (Admin emergency kill-switch)
# ═══════════════════════════════════════════════════════════


def build_set_paused(paused: bool) -> List[str]:
    """Build CLI args for set_paused."""
    cmd = _base_cmd("portfolio", "set_paused")
    cmd += [
        "--args",
        ADMIN_CAP_ID,
        PORTFOLIO_ID,
        str(paused).lower(),
    ]
    return cmd


def execute_set_paused(paused: bool) -> TxResult:
    """Build and execute set_paused."""
    cmd = build_set_paused(paused)
    result = _run_sui_cmd(cmd)
    label = " PAUSED" if paused else "▶  RESUMED"
    if result.success:
        logger.info(f"{label} TX: {result.digest}")
    else:
        logger.error(f" set_paused failed: {result.error}")
    return result


# ═══════════════════════════════════════════════════════════
#  4. deposit (Admin fund loading)
# ═══════════════════════════════════════════════════════════


def build_deposit(amount_mist: int) -> List[str]:
    """Build CLI args for deposit."""
    cmd = _base_cmd("portfolio", "deposit")
    cmd += [
        "--args",
        ADMIN_CAP_ID,
        PORTFOLIO_ID,
        str(amount_mist),
    ]
    return cmd


def execute_deposit(amount_mist: int) -> TxResult:
    """Build and execute deposit."""
    cmd = build_deposit(amount_mist)
    result = _run_sui_cmd(cmd)
    if result.success:
        logger.info(f" Deposit TX: {result.digest}")
    return result


# ═══════════════════════════════════════════════════════════
#  5. update_limits (Admin guardrail tuning)
# ═══════════════════════════════════════════════════════════


def build_update_limits(
    max_drawdown_bps: int,
    daily_volume_limit_mist: int,
    cooldown_ms: int,
) -> List[str]:
    """Build CLI args for update_limits."""
    cmd = _base_cmd("portfolio", "update_limits")
    cmd += [
        "--args",
        ADMIN_CAP_ID,
        PORTFOLIO_ID,
        str(max_drawdown_bps),
        str(daily_volume_limit_mist),
        str(cooldown_ms),
    ]
    return cmd


def execute_update_limits(
    max_drawdown_bps: int,
    daily_volume_limit_mist: int,
    cooldown_ms: int,
) -> TxResult:
    """Build and execute update_limits."""
    cmd = build_update_limits(max_drawdown_bps, daily_volume_limit_mist, cooldown_ms)
    return _run_sui_cmd(cmd)


# ═══════════════════════════════════════════════════════════
#  6. freeze / unfreeze agent
# ═══════════════════════════════════════════════════════════


def build_freeze_agent(agent_address: str) -> List[str]:
    """Build CLI args for freeze_agent."""
    cmd = _base_cmd("portfolio", "freeze_agent")
    cmd += ["--args", ADMIN_CAP_ID, PORTFOLIO_ID, agent_address]
    return cmd


def build_unfreeze_agent(agent_address: str) -> List[str]:
    """Build CLI args for unfreeze_agent."""
    cmd = _base_cmd("portfolio", "unfreeze_agent")
    cmd += ["--args", ADMIN_CAP_ID, PORTFOLIO_ID, agent_address]
    return cmd


def execute_freeze_agent(agent_address: str) -> TxResult:
    return _run_sui_cmd(build_freeze_agent(agent_address))


def execute_unfreeze_agent(agent_address: str) -> TxResult:
    return _run_sui_cmd(build_unfreeze_agent(agent_address))


# ═══════════════════════════════════════════════════════════
#  7. atomic_rebalance (multiple swaps, all-or-nothing)
# ═══════════════════════════════════════════════════════════


def build_atomic_rebalance(
    swap_amounts: List[int],
    swap_min_outputs: List[int],
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> List[str]:
    """Build CLI args for atomic_rebalance."""
    if len(swap_amounts) != len(swap_min_outputs):
        raise ValueError("swap_amounts and swap_min_outputs must have the same length")
    if not swap_amounts:
        raise ValueError("At least one swap is required")

    cmd = _base_cmd("portfolio", "atomic_rebalance")
    cmd += [
        "--args",
        AGENT_CAP_ID,
        PORTFOLIO_ID,
        json.dumps(swap_amounts),
        json.dumps(swap_min_outputs),
        str(is_quantum_optimized).lower(),
        str(quantum_optimization_score),
        SUI_CLOCK,
    ]
    return cmd


def execute_atomic_rebalance(
    swap_amounts: List[int],
    swap_min_outputs: List[int],
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> TxResult:
    """Build and execute atomic_rebalance."""
    cmd = build_atomic_rebalance(
        swap_amounts,
        swap_min_outputs,
        is_quantum_optimized,
        quantum_optimization_score,
    )
    result = _run_sui_cmd(cmd)
    if result.success:
        logger.info(f" Atomic rebalance TX: {result.digest} ({len(swap_amounts)} swaps)")
    return result


# ═══════════════════════════════════════════════════════════
#  8. oracle_validated_swap (single swap with price check)
# ═══════════════════════════════════════════════════════════


def build_oracle_validated_swap(
    amount_mist: int,
    min_output: int,
    oracle_price_x8: int,
    expected_price_x8: int,
    oracle_timestamp_ms: int,
    asset_symbol: str,
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> List[str]:
    """Build CLI args for oracle_validated_swap."""
    if not ORACLE_CONFIG_ID:
        raise ValueError("ORACLE_CONFIG_ID not configured in .env")

    # Encode asset_symbol as vector<u8>
    symbol_bytes = list(asset_symbol.encode("utf-8"))

    cmd = _base_cmd("portfolio", "oracle_validated_swap")
    cmd += [
        "--args",
        AGENT_CAP_ID,
        PORTFOLIO_ID,
        ORACLE_CONFIG_ID,
        str(amount_mist),
        str(min_output),
        str(oracle_price_x8),
        str(expected_price_x8),
        str(oracle_timestamp_ms),
        json.dumps(symbol_bytes),
        str(is_quantum_optimized).lower(),
        str(quantum_optimization_score),
        SUI_CLOCK,
    ]
    return cmd


def execute_oracle_validated_swap(
    amount_mist: int,
    min_output: int,
    oracle_price_x8: int,
    expected_price_x8: int,
    oracle_timestamp_ms: int,
    asset_symbol: str,
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> TxResult:
    """Build and execute oracle_validated_swap."""
    cmd = build_oracle_validated_swap(
        amount_mist,
        min_output,
        oracle_price_x8,
        expected_price_x8,
        oracle_timestamp_ms,
        asset_symbol,
        is_quantum_optimized,
        quantum_optimization_score,
    )
    result = _run_sui_cmd(cmd)
    if result.success:
        logger.info(
            f" Oracle swap TX: {result.digest}, "
            f"oracle=${oracle_price_x8 / 1e8:.4f}, expected=${expected_price_x8 / 1e8:.4f}"
        )
    return result


# ═══════════════════════════════════════════════════════════
#  9. oracle_atomic_rebalance (the gold standard)
# ═══════════════════════════════════════════════════════════


def build_oracle_atomic_rebalance(
    swap_amounts: List[int],
    swap_min_outputs: List[int],
    oracle_prices_x8: List[int],
    expected_prices_x8: List[int],
    oracle_timestamps_ms: List[int],
    asset_symbols: List[str],
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> List[str]:
    """Build CLI args for oracle_atomic_rebalance."""
    if not ORACLE_CONFIG_ID:
        raise ValueError("ORACLE_CONFIG_ID not configured in .env")

    n = len(swap_amounts)
    if not all(
        len(a) == n
        for a in [
            swap_min_outputs,
            oracle_prices_x8,
            expected_prices_x8,
            oracle_timestamps_ms,
            asset_symbols,
        ]
    ):
        raise ValueError("All parameter arrays must have the same length")

    # Encode asset_symbols as vector<vector<u8>>
    symbol_bytes = [list(s.encode("utf-8")) for s in asset_symbols]

    cmd = _base_cmd("portfolio", "oracle_atomic_rebalance")
    cmd += [
        "--args",
        AGENT_CAP_ID,
        PORTFOLIO_ID,
        ORACLE_CONFIG_ID,
        json.dumps(swap_amounts),
        json.dumps(swap_min_outputs),
        json.dumps(oracle_prices_x8),
        json.dumps(expected_prices_x8),
        json.dumps(oracle_timestamps_ms),
        json.dumps(symbol_bytes),
        str(is_quantum_optimized).lower(),
        str(quantum_optimization_score),
        SUI_CLOCK,
    ]
    return cmd


def execute_oracle_atomic_rebalance(
    swap_amounts: List[int],
    swap_min_outputs: List[int],
    oracle_prices_x8: List[int],
    expected_prices_x8: List[int],
    oracle_timestamps_ms: List[int],
    asset_symbols: List[str],
    is_quantum_optimized: bool = True,
    quantum_optimization_score: int = 0,
) -> TxResult:
    """Build and execute oracle_atomic_rebalance."""
    cmd = build_oracle_atomic_rebalance(
        swap_amounts,
        swap_min_outputs,
        oracle_prices_x8,
        expected_prices_x8,
        oracle_timestamps_ms,
        asset_symbols,
        is_quantum_optimized,
        quantum_optimization_score,
    )
    return _run_sui_cmd(cmd)


# ═══════════════════════════════════════════════════════════
#  10. update_oracle_config (Admin)
# ═══════════════════════════════════════════════════════════


def build_update_oracle_config(
    max_slippage_bps: int,
    max_staleness_ms: int,
    enabled: bool,
) -> List[str]:
    """Build CLI args for update_oracle_config."""
    if not ORACLE_CONFIG_ID:
        raise ValueError("ORACLE_CONFIG_ID not configured in .env")

    cmd = _base_cmd("oracle", "update_oracle_config")
    cmd += [
        "--args",
        ADMIN_CAP_ID,
        ORACLE_CONFIG_ID,
        str(max_slippage_bps),
        str(max_staleness_ms),
        str(enabled).lower(),
    ]
    return cmd


def execute_update_oracle_config(
    max_slippage_bps: int,
    max_staleness_ms: int,
    enabled: bool,
) -> TxResult:
    """Build and execute update_oracle_config."""
    cmd = build_update_oracle_config(max_slippage_bps, max_staleness_ms, enabled)
    return _run_sui_cmd(cmd)


# ═══════════════════════════════════════════════════════════
#  11. audit_trail::log_execution
# ═══════════════════════════════════════════════════════════


def build_log_execution(
    proof_hash: bytes,
    amount: int,
    quantum_score: int,
) -> List[str]:
    """Build CLI args for audit_trail::log_execution."""
    cmd = _base_cmd("audit_trail", "log_execution")
    cmd += [
        "--args",
        AGENT_CAP_ID,
        json.dumps(list(proof_hash)),
        str(amount),
        str(quantum_score),
        SUI_CLOCK,
    ]
    return cmd


def execute_log_execution(
    proof_hash: bytes,
    amount: int,
    quantum_score: int,
) -> TxResult:
    """Build and execute log_execution."""
    cmd = build_log_execution(proof_hash, amount, quantum_score)
    return _run_sui_cmd(cmd)


# ═══════════════════════════════════════════════════════════
#  DRY-RUN HELPER
# ═══════════════════════════════════════════════════════════


def dry_run_rebalance(
    amount_mist: int,
    is_quantum_optimized: bool = True,
) -> TxResult:
    """
    Dry-run execute_rebalance using `sui client call --dry-run`.
    Returns success/failure without submitting to chain.
    """
    cmd = build_execute_rebalance(amount_mist, is_quantum_optimized)
    # Add --dry-run flag
    cmd.insert(cmd.index("--json"), "--dry-run")
    return _run_sui_cmd(cmd)


def dry_run_swap(
    amount_mist: int,
    min_output: int = 0,
    quantum_score: int = 0,
) -> TxResult:
    """Dry-run swap_and_rebalance."""
    cmd = build_swap_and_rebalance(amount_mist, min_output, True, quantum_score)
    cmd.insert(cmd.index("--json"), "--dry-run")
    return _run_sui_cmd(cmd)
