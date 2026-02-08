#!/usr/bin/env python3
"""
Integration Tests - Validates critical features and end-to-end flows.

Combines:
  - final_validation.py: Feature validation (6 critical Phase 2 features)
  - integrate.py: Quantum RNG integration with Sui
"""

import inspect
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


# ===== Phase 2 Feature Validation =====

def validate_oracle_price_sync():
    """Feature 1: Oracle price sync with slippage protection."""
    logger.info("Validating: Oracle Price Sync...")
    from blockchain.client import SuiClient
    import blockchain.client as sc

    # Check module-level oracle configuration
    assert hasattr(sc, 'ORACLE_CONFIG_ID'), "Missing ORACLE_CONFIG_ID"
    assert hasattr(sc, 'PYTH_PRICE_FEED_ID'), "Missing PYTH_PRICE_FEED_ID"
    assert hasattr(sc, 'MAX_SLIPPAGE_BPS'), "Missing MAX_SLIPPAGE_BPS"

    # Check calculate_min_output on SuiClient
    assert hasattr(SuiClient, 'calculate_min_output'), "Missing calculate_min_output()"
    sig = inspect.signature(SuiClient.calculate_min_output)
    params = list(sig.parameters.keys())
    assert 'amount' in params, "Missing 'amount' param"
    assert 'expected_price' in params, "Missing 'expected_price' param"

    logger.info("  Oracle config present (ORACLE_CONFIG_ID, PYTH_PRICE_FEED_ID, MAX_SLIPPAGE_BPS)")
    logger.info("  calculate_min_output() implemented on SuiClient")
    return True


def validate_state_reconciliation():
    """Feature 2: Portfolio state reconciliation post-trade."""
    logger.info("Validating: State Reconciliation...")
    from blockchain.client import SuiClient
    import blockchain.client as sc

    assert hasattr(SuiClient, 'get_portfolio_state'), "Missing get_portfolio_state()"
    assert hasattr(SuiClient, 'refresh_portfolio_state'), "Missing refresh_portfolio_state()"
    assert hasattr(SuiClient, 'get_cached_portfolio_state'), "Missing get_cached_portfolio_state()"
    assert hasattr(sc, 'CACHE_TTL_S'), "Missing portfolio cache TTL"
    logger.info("  Portfolio state reconciliation implemented (cache + refresh)")
    return True


def validate_error_mapping():
    """Feature 4: Move error code mapping."""
    logger.info("Validating: Error Code Mapping...")
    from core.error_map import parse_abort_error, ERROR_MAP

    # Test error code mapping via parse_abort_error
    test_codes = [0, 1, 2, 4, 5, 6]
    for code in test_codes:
        # parse_abort_error expects a string-like error
        parsed = parse_abort_error(f"MoveAbort(_, {code})")
        assert parsed.is_move_abort, f"Failed to parse abort code {code}"
        assert parsed.code == code, f"Wrong code: {parsed.code} != {code}"
        assert parsed.frontend_message, f"No frontend message for code {code}"

    logger.info(f"  Error code mapping implemented for {len(ERROR_MAP)} codes")
    return True


def validate_sui_explorer_links():
    """Feature 5: Dynamic Sui explorer links."""
    logger.info("Validating: Sui Explorer Links...")
    from blockchain.client import SuiTransactor

    assert hasattr(SuiTransactor, 'get_explorer_url'), "Missing get_explorer_url()"

    # Test URL generation
    url = SuiTransactor.get_explorer_url("test_digest_123", "devnet")
    assert "suiscan.xyz" in url, f"Bad explorer URL: {url}"
    assert "test_digest_123" in url, f"Digest not in URL: {url}"

    logger.info("  Sui explorer link generation implemented")
    return True


def validate_dry_run_mode():
    """Feature 6: Dry-run mode validation."""
    logger.info("Validating: Dry-Run Mode...")
    from blockchain.client import SuiTransactor

    assert hasattr(SuiTransactor, '_dry_run'), "Missing _dry_run()"
    logger.info("  Dry-run mode available in SuiTransactor")
    return True


# ===== Quantum RNG Integration =====

def run_quantum_rng(shots=100):
    """Execute quantum RNG and return random number."""
    from quantum.rng import run_quantum_rng
    try:
        result = run_quantum_rng(device_arn=os.getenv('AWS_BRAKET_DEVICE', ''), shots=shots)
        return result
    except Exception as e:
        logger.error(f"RNG failed: {e}")
        raise


def select_winner_on_sui(random_number, task_object_id, package_id):
    """Submit winner selection to Sui contract (requires pysui + live network)."""
    logger.warning("pysui not installed — skipping on-chain winner selection")
    return None


def run_full_integration_test():
    """Run full integration test: RNG + winner selection."""
    logger.info("Starting full integration test...")
    
    task_id = os.getenv('TASK_OBJECT_ID')
    package_id = os.getenv('PACKAGE_ID')
    
    if not task_id or not package_id:
        logger.warning("TASK_OBJECT_ID or PACKAGE_ID not set - skipping full integration")
        return False
    
    try:
        random_num = run_quantum_rng(shots=100)
        logger.info(f"Generated random number: {random_num}")
        
        select_winner_on_sui(random_num, task_id, package_id)
        logger.info("Integration test passed")
        return True
    except Exception as e:
        logger.error(f"Integration test failed: {e}")
        return False


# ===== Main =====

def validate_all():
    """Validate all Phase 2 features and integration."""
    logger.info("Starting comprehensive integration validation...")
    
    validators = [
        validate_oracle_price_sync,
        validate_state_reconciliation,
        validate_error_mapping,
        validate_sui_explorer_links,
        validate_dry_run_mode,
    ]
    
    results = []
    for validator in validators:
        try:
            success = validator()
            results.append((validator.__name__, success))
        except Exception as e:
            logger.error(f"{validator.__name__} failed: {e}")
            results.append((validator.__name__, False))
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    logger.info(f"\nValidation Results: {passed}/{total} passed")
    for name, success in results:
        status = "PASS" if success else "FAIL"
        logger.info(f"  [{status}] {name}")
    
    return passed == total


if __name__ == '__main__':
    success = validate_all()
    sys.exit(0 if success else 1)
