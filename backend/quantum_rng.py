#!/usr/bin/env python3
"""
Quantum RNG using AWS Braket.

Default: uses the SV1 simulator for development. To use real hardware, set
the `--device` argument or the `AWS_BRAKET_DEVICE` environment variable to
the ARN of a real device (e.g. an IonQ or Rigetti device ARN).

Requires AWS credentials configured in the environment or via AWS CLI.
"""
import os
import argparse
import json
import sys

from braket.aws import AwsDevice
from braket.circuits import Circuit


def run_quantum_rng(device_arn: str, shots: int):
    device = AwsDevice(device_arn)
    circuit = Circuit().h(0).measure(0)
    task = device.run(circuit, shots=shots)
    result = task.result()
    return result.measurement_counts


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
