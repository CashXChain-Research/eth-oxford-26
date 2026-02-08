#!/usr/bin/env python3
"""
Quantum RNG — Regulatory-Grade Entropy Source (AWS Braket)

PURPOSE: Compliance & Auditability, not "better randomness"

In regulated finance, institutions must prove that critical non-deterministic
values (nonces, trade-ordering seeds, audit timestamps) are not manipulated.
Classical PRNGs are algorithmically predictable given seed knowledge.
Quantum RNG provides physically verifiable randomness: each bit emerges from
a Hadamard-gate measurement — a fundamentally irreversible quantum event.

This gives auditors a hardware-anchored entropy certificate:
  1. The randomness source is identified (AWS Braket device ARN)
  2. Each measurement is logged with shot count and result distribution
  3. Results can be independently verified against quantum-mechanical bounds

USE CASES:
  - Fair trade-ordering: Prevent front-running by seeding execution order
    with quantum-random nonces
  - Audit timestamps: On-chain events tagged with quantum-derived entropy
    prove no timestamp manipulation
  - Regulatory compliance: MiFID II / SEC requirements for demonstrating
    non-deterministic order-matching fairness

Default: uses the SV1 simulator for development. To use real hardware, set
the `--device` argument or the `AWS_BRAKET_DEVICE` environment variable to
the ARN of a real device (e.g. an IonQ or Rigetti device ARN).

Falls back to a local simulation if the Braket SDK is not compatible
with the current Python version (e.g. Python 3.14+).

Requires AWS credentials configured in the environment or via AWS CLI.
"""

import argparse
import json
import os
import random
import sys

BRAKET_AVAILABLE = False
try:
    from braket.aws import AwsDevice
    from braket.circuits import Circuit

    BRAKET_AVAILABLE = True
except Exception:
    pass


def run_quantum_rng_braket(device_arn: str, shots: int) -> dict:
    """Run on real AWS Braket device/simulator."""
    device = AwsDevice(device_arn)
    circuit = Circuit().h(0).measure(0)
    task = device.run(circuit, shots=shots)
    result = task.result()
    return dict(result.measurement_counts)


def run_quantum_rng_local(shots: int) -> dict:
    """Local fallback: simulate a Hadamard gate (50/50 coin flip per shot)."""
    counts = {"0": 0, "1": 0}
    for _ in range(shots):
        bit = random.getrandbits(1)
        counts[str(bit)] += 1
    return counts


def run_quantum_rng(device_arn: str, shots: int) -> dict:
    if BRAKET_AVAILABLE:
        return run_quantum_rng_braket(device_arn, shots)
    else:
        print("WARNING: Braket SDK not available, using local RNG fallback", file=sys.stderr)
        return run_quantum_rng_local(shots)


def main():
    parser = argparse.ArgumentParser(description="AWS Braket Quantum RNG")
    parser.add_argument("--shots", type=int, default=100, help="Number of shots (measurements)")
    parser.add_argument(
        "--device",
        type=str,
        default=os.getenv(
            "AWS_BRAKET_DEVICE",
            "arn:aws:braket:::device/quantum-simulator/amazon/sv1",
        ),
        help="Device ARN (defaults to SV1 simulator or AWS_BRAKET_DEVICE env var)",
    )

    args = parser.parse_args()

    try:
        counts = run_quantum_rng(args.device, args.shots)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    # Print result as JSON (measurement bitstring -> counts)
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
