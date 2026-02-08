#!/usr/bin/env python3
"""
Stress test for error_map.py — validate all 11 Move error codes.

Run this to ensure all errors are correctly mapped to frontend messages.
Useful before demo to verify error rendering on the frontend.

Usage:
    python test_error_map.py
    python test_error_map.py --verbose

Author: Korbinian Weber — ETH Oxford Hackathon 2026
"""

import argparse
import json
from core.error_map import ERROR_MAP, MoveError


def test_error_map_completeness():
    """Verify all required error codes are present."""
    print("\n" + "=" * 70)
    print("ERROR MAP COMPLETENESS TEST")
    print("=" * 70)

    required_codes = {
        0: "EInvalidAgent",
        1: "EAgentFrozen",
        2: "ECooldownActive",
        3: "EVolumeExceeded",
        4: "EDrawdownExceeded",
        5: "EInsufficientBalance",
        6: "EPaused",
        7: "ESlippageExceeded",
        8: "EAtomicRebalanceFailed",
        9: "ESwapCountMismatch",
        10: "EPostRebalanceDrawdown",
        11: "EProtocolNotWhitelisted",
    }

    missing = []
    for code, name in required_codes.items():
        if code not in ERROR_MAP:
            missing.append((code, name))
            print(f" Code {code:2d} ({name:30s}): MISSING")
        else:
            error = ERROR_MAP[code]
            print(
                f" Code {code:2d} ({name:30s}): {error.constant:25s} "
                f"→ {error.frontend_message[:40]}"
            )

    if missing:
        print(f"\n  FAILED: {len(missing)} errors missing from ERROR_MAP")
        return False
    else:
        print(f"\n PASSED: All {len(required_codes)} error codes present")
        return True


def test_error_map_structure():
    """Verify each error has all required fields."""
    print("\n" + "=" * 70)
    print("ERROR MAP STRUCTURE TEST")
    print("=" * 70)

    required_fields = {
        "code",
        "constant",
        "module",
        "severity",
        "frontend_message",
        "dev_message",
        "recovery",
    }
    issues = []

    for code, error in sorted(ERROR_MAP.items()):
        missing_fields = required_fields - set(vars(error).keys())
        if missing_fields:
            issues.append((code, missing_fields))
            print(f" Code {code}: Missing fields {missing_fields}")
        else:
            print(f" Code {code}: All fields present")

    if issues:
        print(f"\n  FAILED: {len(issues)} errors have missing fields")
        return False
    else:
        print(f"\n PASSED: All {len(ERROR_MAP)} errors have complete structure")
        return True


def test_error_map_severity():
    """Verify severity levels are valid."""
    print("\n" + "=" * 70)
    print("ERROR MAP SEVERITY LEVEL TEST")
    print("=" * 70)

    valid_severities = {"warning", "error", "critical"}
    issues = []

    for code, error in sorted(ERROR_MAP.items()):
        if error.severity not in valid_severities:
            issues.append((code, error.severity))
            print(f" Code {code}: Invalid severity '{error.severity}'")
        else:
            print(f" Code {code}: Severity '{error.severity}' valid")

    if issues:
        print(f"\n  FAILED: {len(issues)} errors have invalid severity")
        return False
    else:
        print(f"\n PASSED: All {len(ERROR_MAP)} errors have valid severity")
        return True


def test_error_frontend_messages():
    """Verify frontend messages are non-empty and meaningful."""
    print("\n" + "=" * 70)
    print("ERROR MAP FRONTEND MESSAGE TEST")
    print("=" * 70)

    issues = []

    for code, error in sorted(ERROR_MAP.items()):
        msg = error.frontend_message
        if not msg or len(msg) < 10:
            issues.append((code, f"Too short: '{msg}'"))
            print(f" Code {code}: Message too short: '{msg}'")
        elif "PLACEHOLDER" in msg or "TODO" in msg:
            issues.append((code, f"Incomplete: '{msg}'"))
            print(f" Code {code}: Message incomplete: '{msg}'")
        else:
            print(f" Code {code}: Message ok ({len(msg)} chars)")

    if issues:
        print(f"\n  FAILED: {len(issues)} errors have poor frontend messages")
        return False
    else:
        print(f"\n PASSED: All {len(ERROR_MAP)} errors have good frontend messages")
        return True


def test_error_uniqueness():
    """Verify no duplicate constants or codes."""
    print("\n" + "=" * 70)
    print("ERROR MAP UNIQUENESS TEST")
    print("=" * 70)

    codes_seen = set()
    constants_seen = set()
    issues = []

    for code, error in sorted(ERROR_MAP.items()):
        if code in codes_seen:
            issues.append(f"Duplicate code: {code}")
            print(f" Duplicate code {code}")
        else:
            codes_seen.add(code)

        if error.constant in constants_seen:
            issues.append(f"Duplicate constant: {error.constant}")
            print(f" Duplicate constant '{error.constant}'")
        else:
            constants_seen.add(error.constant)
            print(f" Code {code} ({error.constant}): Unique")

    if issues:
        print(f"\n  FAILED: {len(issues)} duplicate issues found")
        return False
    else:
        print(f"\n PASSED: All codes and constants are unique")
        return True


def generate_error_report(verbose: bool = False):
    """Generate a detailed error map report."""
    print("\n" + "=" * 70)
    print("ERROR MAP DETAILED REPORT")
    print("=" * 70)

    by_severity = {}
    for code, error in sorted(ERROR_MAP.items()):
        if error.severity not in by_severity:
            by_severity[error.severity] = []
        by_severity[error.severity].append((code, error))

    for severity in ["warning", "error", "critical"]:
        if severity in by_severity:
            errors = by_severity[severity]
            print(f"\n{severity.upper()} ({len(errors)} errors):")
            for code, error in errors:
                print(f"  Code {code:2d}: {error.constant:30s}")
                print(f"    Frontend: {error.frontend_message}")
                if verbose:
                    print(f"    Dev: {error.dev_message}")
                    print(f"    Recovery: {error.recovery}")
                    print(f"    Module: {error.module}")


def main():
    parser = argparse.ArgumentParser(description="Stress test the error_map.py")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed messages")
    parser.add_argument("--report", "-r", action="store_true", help="Generate full report")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    results = {}

    # Run all tests
    results["completeness"] = test_error_map_completeness()
    results["structure"] = test_error_map_structure()
    results["severity"] = test_error_map_severity()
    results["frontend_messages"] = test_error_frontend_messages()
    results["uniqueness"] = test_error_uniqueness()

    if args.report:
        generate_error_report(verbose=args.verbose)

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if args.json:
        print("\nJSON Output:")
        print(
            json.dumps(
                {
                    "test_results": results,
                    "summary": {"passed": passed, "total": total},
                    "error_count": len(ERROR_MAP),
                },
                indent=2,
            )
        )

    if all(results.values()):
        print("\n ALL TESTS PASSED")
        return 0
    else:
        print("\n SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit(main())
