#!/usr/bin/env python3
"""
Robust Relayer / Oracle for quantum_vault on Sui.

Production-grade event listener with:
  - Exponential backoff on failures
  - Cursor-based event tracking (no duplicates across restarts)
  - Health monitoring & metrics
  - Graceful shutdown (SIGINT / SIGTERM)
  - Async QRNG triggering (non-blocking)
  - Auto-reconnect on RPC failures
  - Integration with quantum RNG + agent pipeline

Listens to:
  - AgentRegistered  → triggers QRNG → select_winner
  - TaskCreated      → logs new task

Start:
  python relayer.py                  # production mode
  python relayer.py --demo           # force demo mode

Author: Valentin Israel & Korbinian — ETH Oxford Hackathon 2026
"""

import asyncio
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from dotenv import load_dotenv

load_dotenv()

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("relayer")

# ── httpx (async HTTP) ───────────────────────────────────────

try:
    import httpx
except ImportError:
    logger.error("httpx not installed. Install with: pip install httpx")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

SUI_RPC_URL = os.getenv("SUI_RPC_URL", "https://fullnode.devnet.sui.io:443")
PACKAGE_ID = os.getenv("PACKAGE_ID", "")
TASK_OBJECT_ID = os.getenv("TASK_OBJECT_ID", "")
PORTFOLIO_OBJECT_ID = os.getenv("PORTFOLIO_OBJECT_ID", "")
ADMIN_CAP_ID = os.getenv("ADMIN_CAP_ID", "")
AGENT_CAP_ID = os.getenv("AGENT_CAP_ID", "")
SHOTS = int(os.getenv("SHOTS", "100"))

# Polling / retry
POLL_INTERVAL_S = int(os.getenv("POLL_INTERVAL", "3"))
MAX_BACKOFF_S = int(os.getenv("MAX_BACKOFF", "60"))
INITIAL_BACKOFF_S = 1
HEALTH_LOG_INTERVAL_S = 60


# ═══════════════════════════════════════════════════════════
#  HEALTH METRICS
# ═══════════════════════════════════════════════════════════


@dataclass
class RelayerMetrics:
    """Runtime health counters."""

    started_at: float = 0.0
    events_processed: int = 0
    events_skipped: int = 0
    rng_triggered: int = 0
    rng_failures: int = 0
    rpc_errors: int = 0
    last_event_time: float = 0.0
    last_poll_time: float = 0.0
    consecutive_errors: int = 0
    current_backoff: float = INITIAL_BACKOFF_S

    def reset_backoff(self):
        self.consecutive_errors = 0
        self.current_backoff = INITIAL_BACKOFF_S

    def increase_backoff(self):
        self.consecutive_errors += 1
        self.current_backoff = min(self.current_backoff * 2, MAX_BACKOFF_S)

    def summary(self) -> Dict[str, Any]:
        uptime = time.time() - self.started_at if self.started_at else 0
        return {
            "uptime_s": round(uptime, 1),
            "events_processed": self.events_processed,
            "events_skipped": self.events_skipped,
            "rng_triggered": self.rng_triggered,
            "rng_failures": self.rng_failures,
            "rpc_errors": self.rpc_errors,
            "consecutive_errors": self.consecutive_errors,
            "current_backoff_s": self.current_backoff,
        }


metrics = RelayerMetrics()


# ═══════════════════════════════════════════════════════════
#  CURSOR PERSISTENCE  (survive restarts)
# ═══════════════════════════════════════════════════════════

CURSOR_FILE = os.path.join(os.path.dirname(__file__) or ".", ".relayer_cursor.json")


def load_cursors() -> Dict[str, Any]:
    try:
        with open(CURSOR_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cursors(cursors: Dict[str, Any]):
    try:
        with open(CURSOR_FILE, "w") as f:
            json.dump(cursors, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist cursors: {e}")


# ═══════════════════════════════════════════════════════════
#  ASYNC SUI RPC CLIENT
# ═══════════════════════════════════════════════════════════


class AsyncSuiRPC:
    """Async JSON-RPC client with connection pooling."""

    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self._req_id = 0
        self._client: Optional[httpx.AsyncClient] = None

    async def _ensure_client(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=15)

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def call(self, method: str, params: list) -> Any:
        await self._ensure_client()
        self._req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
            "params": params,
        }
        resp = await self._client.post(self.rpc_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result", {})

    async def query_events(
        self,
        event_type: str,
        cursor: Optional[Dict] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        return await self.call(
            "suix_queryEvents",
            [
                {"MoveEventType": event_type},
                cursor,
                limit,
                False,
            ],
        )

    async def get_object(self, object_id: str) -> Dict[str, Any]:
        return await self.call(
            "sui_getObject",
            [
                object_id,
                {"showContent": True, "showType": True},
            ],
        )


# ═══════════════════════════════════════════════════════════
#  QUANTUM RNG (async, non-blocking)
# ═══════════════════════════════════════════════════════════


async def get_quantum_random(shots: int) -> Optional[int]:
    """Run quantum_rng.py asynchronously. Returns None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "quantum_rng.py",
            "--shots",
            str(shots),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.path.dirname(__file__) or ".",
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)

        if proc.returncode != 0:
            logger.error(f"QRNG failed (rc={proc.returncode}): {stderr.decode().strip()}")
            metrics.rng_failures += 1
            return None

        counts = json.loads(stdout.decode().strip())
        random_num = counts.get("1", 0)
        logger.info(f"  QRNG result: {random_num} (counts={counts})")
        metrics.rng_triggered += 1
        return random_num

    except asyncio.TimeoutError:
        logger.error("  QRNG timed out (90s)")
        metrics.rng_failures += 1
        return None
    except Exception as e:
        logger.error(f"  QRNG error: {e}")
        metrics.rng_failures += 1
        return None


# ═══════════════════════════════════════════════════════════
#  ON-CHAIN CALLS
# ═══════════════════════════════════════════════════════════


async def call_select_winner(random_number: int) -> bool:
    """Call select_winner via Sui CLI (async)."""
    if not PACKAGE_ID or PACKAGE_ID == "0x..." or not TASK_OBJECT_ID or TASK_OBJECT_ID == "0x...":
        logger.info(f"[DEMO] select_winner(random={random_number})")
        return True

    cmd = [
        "sui",
        "client",
        "call",
        "--package",
        PACKAGE_ID,
        "--module",
        "ai_task",
        "--function",
        "select_winner",
        "--args",
        TASK_OBJECT_ID,
        str(random_number),
        "--gas-budget",
        "10000000",
        "--json",
    ]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

        if proc.returncode == 0:
            tx = json.loads(stdout.decode())
            logger.info(f" select_winner TX: {tx.get('digest', 'ok')}")
            return True
        else:
            logger.error(f" select_winner failed: {stderr.decode().strip()}")
            return False

    except FileNotFoundError:
        logger.warning("sui CLI not found — dry-run mode")
        return True
    except asyncio.TimeoutError:
        logger.error("select_winner timed out (30s)")
        return False
    except Exception as e:
        logger.error(f"select_winner error: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  EVENT HANDLERS
# ═══════════════════════════════════════════════════════════


async def handle_agent_registered(
    rpc: AsyncSuiRPC,
    event_data: Dict[str, Any],
    tx_digest: str,
) -> bool:
    """
    AgentRegistered → QRNG → select_winner.
    The core oracle pipeline.
    """
    agent = event_data.get("agent", "?")
    reputation = event_data.get("reputation", 0)
    logger.info(f" AgentRegistered: agent={agent}, " f"reputation={reputation}, tx={tx_digest}")

    # 1. Quantum random number
    logger.info("  Triggering AWS Braket quantum RNG …")
    random_num = await get_quantum_random(SHOTS)
    if random_num is None:
        logger.error(" QRNG failed — skipping winner selection")
        return False

    # 2. On-chain winner selection
    ok = await call_select_winner(random_num)
    if ok:
        logger.info(f" Winner selection complete (quantum random: {random_num})")
    return ok


async def handle_task_created(
    rpc: AsyncSuiRPC,
    event_data: Dict[str, Any],
    tx_digest: str,
):
    """TaskCreated — informational log."""
    logger.info(
        f" TaskCreated: admin={event_data.get('admin', '?')}, "
        f"task_id={event_data.get('task_id', '?')}, tx={tx_digest}"
    )


# ═══════════════════════════════════════════════════════════
#  RELAYER ENGINE
# ═══════════════════════════════════════════════════════════


class Relayer:
    """
    Production-grade event-driven relayer.

    Features:
      • Exponential backoff (1s → 60s max)
      • Cursor-based dedup (persisted to .relayer_cursor.json)
      • Graceful SIGINT / SIGTERM handling
      • Periodic health logging
      • Auto-reconnect on RPC failures
    """

    def __init__(self, force_demo: bool = False):
        self.rpc = AsyncSuiRPC(SUI_RPC_URL)
        self.running = True
        self.cursors = load_cursors()
        self.processed: Set[str] = set()
        self.demo_mode = force_demo or (
            not PACKAGE_ID
            or PACKAGE_ID == "0x..."
            or not TASK_OBJECT_ID
            or TASK_OBJECT_ID == "0x..."
        )

        # Map event types to handlers
        if PACKAGE_ID and PACKAGE_ID != "0x...":
            self.event_handlers = {
                f"{PACKAGE_ID}::ai_task::AgentRegistered": handle_agent_registered,
                f"{PACKAGE_ID}::ai_task::TaskCreated": handle_task_created,
            }
        else:
            self.event_handlers = {}

    # ── Signal handling ──────────────────────────────────────

    def _setup_signals(self):
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._shutdown)

    def _shutdown(self):
        logger.info(" Shutdown signal — saving state …")
        self.running = False
        save_cursors(self.cursors)
        logger.info(f" Final metrics: {json.dumps(metrics.summary(), indent=2)}")

    # ── Event polling ────────────────────────────────────────

    async def _poll_event_type(self, event_type: str):
        cursor = self.cursors.get(event_type)
        result = await self.rpc.query_events(event_type, cursor=cursor, limit=25)

        events = result.get("data", [])
        next_cursor = result.get("nextCursor")

        for event in events:
            ev_id = event.get("id", {})
            dedup_key = f"{ev_id.get('txDigest', '')}:{ev_id.get('eventSeq', '')}"

            if dedup_key in self.processed:
                metrics.events_skipped += 1
                continue

            self.processed.add(dedup_key)
            parsed = event.get("parsedJson", {})
            tx_digest = ev_id.get("txDigest", "")

            handler = self.event_handlers.get(event_type)
            if handler:
                try:
                    await handler(self.rpc, parsed, tx_digest)
                    metrics.events_processed += 1
                    metrics.last_event_time = time.time()
                except Exception as e:
                    logger.error(f"Handler error [{event_type}]: {e}", exc_info=True)

        if next_cursor:
            self.cursors[event_type] = next_cursor

        # Cap in-memory set
        if len(self.processed) > 10_000:
            self.processed = set(list(self.processed)[-5_000:])

    async def _poll_cycle(self):
        for et in self.event_handlers:
            if not self.running:
                break
            await self._poll_event_type(et)
        metrics.last_poll_time = time.time()

    # ── Health logger ────────────────────────────────────────

    async def _health_loop(self):
        while self.running:
            await asyncio.sleep(HEALTH_LOG_INTERVAL_S)
            logger.info(f" Health: {json.dumps(metrics.summary())}")
            save_cursors(self.cursors)

    # ── Demo mode ────────────────────────────────────────────

    async def _demo_loop(self):
        logger.info(" DEMO MODE — no deployed contract")
        logger.info("   Set PACKAGE_ID + TASK_OBJECT_ID in .env for live mode\n")

        cycle = 0
        while self.running:
            cycle += 1
            logger.info(f"Demo #{cycle} — polling (simulated) …")

            if cycle % 5 == 0:
                logger.info(" Demo: triggering QRNG …")
                rng = await get_quantum_random(SHOTS)
                if rng is not None:
                    logger.info(f" Demo: would call select_winner({rng})")

            await asyncio.sleep(POLL_INTERVAL_S)

    # ── Main loop ────────────────────────────────────────────

    async def run(self):
        metrics.started_at = time.time()
        self._setup_signals()

        logger.info("═" * 60)
        logger.info("   quantum_vault Relayer v2.0")
        logger.info("═" * 60)
        logger.info(f"  RPC:       {SUI_RPC_URL}")
        logger.info(f"  Package:   {PACKAGE_ID or '(not set)'}")
        logger.info(f"  Task:      {TASK_OBJECT_ID or '(not set)'}")
        logger.info(f"  Portfolio: {PORTFOLIO_OBJECT_ID or '(not set)'}")
        logger.info(f"  Poll:      every {POLL_INTERVAL_S}s")
        logger.info(f"  QRNG:      {SHOTS} shots")
        logger.info(f"  Demo:      {self.demo_mode}")
        logger.info(f"  Events:    {len(self.event_handlers)} types")
        logger.info(f"  Cursors:   {len(self.cursors)} loaded")
        logger.info("")

        if self.demo_mode:
            await self._demo_loop()
            return

        health = asyncio.create_task(self._health_loop())

        try:
            while self.running:
                try:
                    await self._poll_cycle()
                    metrics.reset_backoff()
                    save_cursors(self.cursors)
                    await asyncio.sleep(POLL_INTERVAL_S)

                except (httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException) as e:
                    metrics.rpc_errors += 1
                    metrics.increase_backoff()
                    logger.warning(
                        f"  RPC error: {type(e).__name__}: {e} — "
                        f"retry in {metrics.current_backoff:.0f}s "
                        f"(#{metrics.consecutive_errors})"
                    )
                    await self.rpc.close()
                    await asyncio.sleep(metrics.current_backoff)

                except Exception as e:
                    metrics.rpc_errors += 1
                    metrics.increase_backoff()
                    logger.error(
                        f" Unexpected: {e} — retry in {metrics.current_backoff:.0f}s",
                        exc_info=True,
                    )
                    await asyncio.sleep(metrics.current_backoff)

        finally:
            health.cancel()
            await self.rpc.close()
            save_cursors(self.cursors)
            logger.info(" Relayer stopped gracefully")
            logger.info(f" Final: {json.dumps(metrics.summary(), indent=2)}")


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════


def main():
    import argparse

    parser = argparse.ArgumentParser(description="quantum_vault Relayer v2.0")
    parser.add_argument("--demo", action="store_true", help="Force demo mode")
    args = parser.parse_args()

    relayer = Relayer(force_demo=args.demo)
    try:
        asyncio.run(relayer.run())
    except KeyboardInterrupt:
        logger.info(" Interrupted")


if __name__ == "__main__":
    main()
