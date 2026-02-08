#!/usr/bin/env python3
"""Quick smoke-test of all components."""
import os, sys, time

PASS = "✅"
FAIL = "❌"

results = []

def test(name, fn):
    try:
        fn()
        results.append((PASS, name))
    except Exception as e:
        results.append((FAIL, f"{name}: {e}"))

# ═══ TEST 1: QUBO Optimizer ═══
def test_qubo():
    from quantum.optimizer import PortfolioQUBO, QUBOConfig, make_test_universe
    assets, cov = make_test_universe()
    assert len(assets) == 5
    cfg = QUBOConfig(target_assets=3, num_reads=200, use_qpu=False)
    optimizer = PortfolioQUBO(assets, cov, cfg)
    result = optimizer.solve()
    assert result.feasible
    selected = sum(1 for v in result.allocation.values() if v == 1)
    assert selected >= 1
    print(f"  QUBO: {result.solver_used}, {result.solver_time_s:.3f}s, "
          f"selected={selected}, E(r)={result.expected_return:.4f}")

test("QUBO Optimizer", test_qubo)

# ═══ TEST 2: Quantum RNG ═══
def test_rng():
    from quantum.rng import run_quantum_rng_local
    result = run_quantum_rng_local(shots=16)
    total = result.get("0", 0) + result.get("1", 0)
    assert total == 16
    print(f"  RNG: {result}")

test("Quantum RNG (local sim)", test_rng)

# ═══ TEST 3: Sui Devnet RPC ═══
def test_sui_rpc():
    from blockchain.client import SuiClient
    client = SuiClient("https://fullnode.devnet.sui.io:443")
    result = client._call("sui_getLatestCheckpointSequenceNumber", [])
    assert result is not None
    print(f"  Sui devnet checkpoint: {result}")

test("Sui Devnet RPC", test_sui_rpc)

# ═══ TEST 4: Contract deployed? ═══
def test_contract():
    pkg_id = os.getenv("PACKAGE_ID", "")
    if not pkg_id or pkg_id.startswith("0x_") or pkg_id == "0x...":
        raise Exception("PACKAGE_ID not set — contract NOT deployed")
    from blockchain.client import SuiClient
    client = SuiClient("https://fullnode.devnet.sui.io:443")
    obj = client.get_object(pkg_id)
    print(f"  Package found: {pkg_id[:24]}...")

test("Smart Contract on-chain", test_contract)

# ═══ TEST 5: Sui CLI ═══
def test_sui_cli():
    import subprocess
    result = subprocess.run(["sui", "--version"], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0
    print(f"  {result.stdout.strip()}")

test("Sui CLI installed", test_sui_cli)

# ═══ TEST 6: Private Key ═══
def test_wallet():
    pk = os.getenv("SUI_PRIVATE_KEY", "")
    if not pk or pk == "your_sui_private_key_hex":
        raise Exception("SUI_PRIVATE_KEY not set")
    print(f"  Key: {pk[:8]}...")

test("Sui Private Key", test_wallet)

# ═══ TEST 7: LangGraph ═══
def test_langgraph():
    from langgraph.graph import END, StateGraph
    print("  LangGraph OK")

test("LangGraph import", test_langgraph)

# ═══ TEST 8: CoinGecko ═══
def test_market():
    from core.market_data import MarketDataFetcher
    fetcher = MarketDataFetcher()
    assets, cov = fetcher.fetch_prices_and_returns(days=7)
    assert len(assets) >= 3
    print(f"  CoinGecko: {len(assets)} assets")

test("CoinGecko Market Data", test_market)

# ═══ TEST 9: Python version ═══
def test_pyver():
    v = sys.version_info
    print(f"  Python {v.major}.{v.minor}.{v.micro}")
    if v.minor >= 14:
        raise Exception(f"Python {v.major}.{v.minor} too new for LangGraph (needs <=3.12)")

test("Python version compat", test_pyver)

# ═══ RESULTS ═══
print("\n" + "=" * 60)
print("COMPONENT TEST RESULTS")
print("=" * 60)
for icon, msg in results:
    print(f"  {icon} {msg}")
passed = sum(1 for i, _ in results if i == PASS)
failed = sum(1 for i, _ in results if i == FAIL)
print(f"\n  {passed} passed, {failed} failed\n")
if failed > 0:
    print("ACTION ITEMS:")
    for icon, msg in results:
        if icon == FAIL:
            if "3.14" in msg or "Python" in msg:
                print("  → brew install python@3.12 && python3.12 -m venv .venv")
            elif "PACKAGE_ID" in msg:
                print("  → Deploy contract auf Devnet (braucht Sui CLI)")
            elif "PRIVATE_KEY" in msg:
                print("  → .env erstellen mit SUI_PRIVATE_KEY")
            elif "sui CLI" in msg.lower() or "Sui CLI" in msg:
                print("  → brew install sui")
            elif "LangGraph" in msg:
                print("  → Braucht Python <=3.12")
            elif "CoinGecko" in msg:
                print("  → (optional) Mock reicht fuer Demo")
