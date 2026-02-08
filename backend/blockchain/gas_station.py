#!/usr/bin/env python3
"""
gas_station.py — Gas Balance Monitor

Checks agent and admin SUI balances and warns when gas is low.
Can run standalone or be imported into the relayer.

Usage:
    python gas_station.py              # one-shot check
    python gas_station.py --watch      # continuous monitoring
"""

import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from typing import List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════

NETWORK = os.getenv("SUI_NETWORK", "devnet")
RPC_URL = os.getenv("SUI_RPC_URL", f"https://fullnode.{NETWORK}.sui.io:443")

MIN_GAS_MIST = int(os.getenv("MIN_GAS_MIST", "500000000"))  # 0.5 SUI
CRITICAL_GAS_MIST = int(os.getenv("CRITICAL_GAS_MIST", "100000000"))  # 0.1 SUI

FAUCET_URLS = {
    "devnet": "https://faucet.devnet.sui.io/gas",
    "testnet": "https://faucet.testnet.sui.io/v1/gas",
}

# ═══════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════

_rpc_id = 0


def _rpc_call(method: str, params: list) -> dict:
    """Minimal Sui JSON-RPC call."""
    global _rpc_id
    _rpc_id += 1
    payload = {
        "jsonrpc": "2.0",
        "id": _rpc_id,
        "method": method,
        "params": params,
    }
    with httpx.Client(timeout=15) as client:
        resp = client.post(RPC_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        raise RuntimeError(f"RPC error: {data['error']}")
    return data.get("result", {})


def _load_address(env_key: str) -> Optional[str]:
    """Derive a Sui address from a private key env var using the sui CLI."""
    key = os.getenv(env_key)
    if not key:
        return None

    try:
        import subprocess

        # Use sui keytool to convert private key to address
        result = subprocess.run(
            ["sui", "keytool", "show", key],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Parse address from output
            for line in result.stdout.splitlines():
                line = line.strip()
                if line.startswith("Sui Address:") or line.startswith("suiAddress:"):
                    return line.split(":", 1)[1].strip()
                # Also try JSON output
                if '"suiAddress"' in line or '"sui_address"' in line:
                    import json

                    data = json.loads(result.stdout)
                    return data.get("suiAddress", data.get("sui_address", ""))
            # Try parsing as JSON
            import json

            try:
                data = json.loads(result.stdout)
                return data.get("suiAddress", data.get("sui_address", ""))
            except json.JSONDecodeError:
                pass
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Fallback: if key looks like an address, use it directly
    if key.startswith("0x") and len(key) >= 42:
        return key

    return None


@dataclass
class GasStatus:
    address: str
    role: str
    balance_mist: int
    balance_sui: str
    level: str  # 'ok' | 'low' | 'critical' | 'empty'
    message: str


def _format_sui(mist: int) -> str:
    return f"{mist / 1e9:.4f}"


def _check_balance(address: str, role: str) -> GasStatus:
    """Check gas balance for a single address."""
    result = _rpc_call("suix_getCoins", [address, "0x2::sui::SUI", None, None])
    coins = result.get("data", [])
    total = sum(int(c.get("balance", "0")) for c in coins)

    if total == 0:
        level = "empty"
        message = f" {role} hat KEIN Gas! Sofort Faucet nutzen."
    elif total < CRITICAL_GAS_MIST:
        level = "critical"
        message = (
            f" {role} Gas KRITISCH: {_format_sui(total)} SUI — Trades werden bald fehlschlagen!"
        )
    elif total < MIN_GAS_MIST:
        level = "low"
        message = f"🟡 {role} Gas niedrig: {_format_sui(total)} SUI — bald auffüllen."
    else:
        level = "ok"
        message = f"🟢 {role} Gas OK: {_format_sui(total)} SUI"

    return GasStatus(
        address=address,
        role=role,
        balance_mist=total,
        balance_sui=_format_sui(total),
        level=level,
        message=message,
    )


# ═══════════════════════════════════════════════════════════
#  PUBLIC API (importable by relayer)
# ═══════════════════════════════════════════════════════════


def check_all_gas() -> List[GasStatus]:
    """Check gas balances for all configured accounts."""
    results = []

    agent_addr = _load_address("AGENT_PRIVATE_KEY")
    admin_addr = _load_address("ADMIN_PRIVATE_KEY")

    if agent_addr:
        results.append(_check_balance(agent_addr, "Agent (Valentin)"))
    if admin_addr:
        results.append(_check_balance(admin_addr, "Admin (Korbinian)"))

    return results


def is_gas_sufficient() -> bool:
    """True if all accounts have at least 'low' gas."""
    statuses = check_all_gas()
    return all(s.level in ("ok", "low") for s in statuses)


# ═══════════════════════════════════════════════════════════
#  AUTO-FAUCET (devnet/testnet only)
# ═══════════════════════════════════════════════════════════


def _request_faucet(address: str) -> bool:
    url = FAUCET_URLS.get(NETWORK)
    if not url:
        print(f"     Kein Faucet für {NETWORK} verfügbar.")
        return False

    try:
        print(f"    Faucet-Anfrage für {address}...")
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                url,
                json={"FixedAmountRequest": {"recipient": address}},
            )
        if resp.is_success:
            print("    Faucet erfolgreich!")
            return True
        else:
            print(f"    Faucet-Fehler: {resp.status_code} {resp.reason_phrase}")
            return False
    except Exception as e:
        print(f"    Faucet-Fehler: {e}")
        return False


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════


def _print_status() -> List[GasStatus]:
    print("\n═══════════════════════════════════════════════════")
    print("   Gas Station — Balance Monitor")
    print("═══════════════════════════════════════════════════")
    print(f"  Network:  {NETWORK}")
    print(f"  Min Gas:  {_format_sui(MIN_GAS_MIST)} SUI")
    print(f"  Critical: {_format_sui(CRITICAL_GAS_MIST)} SUI\n")

    statuses = check_all_gas()

    if not statuses:
        print("    Keine Keys in .env gefunden (AGENT_PRIVATE_KEY / ADMIN_PRIVATE_KEY)")
        return statuses

    for s in statuses:
        print(f"  {s.message}")
        print(f"     Address: {s.address}")
        print(f"     Balance: {s.balance_mist} MIST\n")

        # Auto-faucet if critical/empty on devnet/testnet
        if s.level in ("critical", "empty") and NETWORK in FAUCET_URLS:
            _request_faucet(s.address)

    return statuses


async def _watch_loop():
    interval = int(os.getenv("GAS_CHECK_INTERVAL", "30000")) / 1000
    print(f"\n   Watch-Modus: Prüfe alle {interval:.0f}s ...\n")

    while True:
        await asyncio.sleep(interval)
        statuses = check_all_gas()
        for s in statuses:
            if s.level != "ok":
                print(f"  {s.message}")
                if s.level in ("critical", "empty") and NETWORK in FAUCET_URLS:
                    _request_faucet(s.address)


def main():
    _print_status()

    if "--watch" in sys.argv:
        asyncio.run(_watch_loop())


if __name__ == "__main__":
    main()
