#!/usr/bin/env python3
"""
Integration script: Run quantum RNG and select winner on Sui contract.
"""
import os
import json
import subprocess
import sys
from dotenv import load_dotenv
from pysui import SuiConfig, SyncClient
from pysui.sui.sui_txn import SyncTransaction
from pysui.sui.sui_types import ObjectID

load_dotenv()  # Load .env file

def get_random_number(counts):
    # Simple: number of '1's
    return counts.get('1', 0)

def run_rng(shots=100):
    # Run the RNG script
    result = subprocess.run([
        sys.executable, 'quantum_rng.py', '--shots', str(shots)
    ], capture_output=True, text=True, cwd=os.path.dirname(__file__))
    if result.returncode != 0:
        raise Exception(f"RNG failed: {result.stderr}")
    counts = json.loads(result.stdout.strip())
    return get_random_number(counts)

def select_winner_on_sui(random_number, task_object_id, package_id):
    # Sui client setup
    config = SuiConfig.default_config()
    client = SyncClient(config)

    # Build transaction
    txn = SyncTransaction(client=client)
    txn.move_call(
        target=f"{package_id}::ai_task::select_winner",
        arguments=[ObjectID(task_object_id), random_number],
    )

    # Sign and execute (assuming signer is set in config)
    result = txn.execute()
    print(f"Winner selected: {result}")

if __name__ == "__main__":
    # Env vars
    task_id = os.getenv('TASK_OBJECT_ID')
    package_id = os.getenv('PACKAGE_ID')  # Set after deploy
    shots = int(os.getenv('SHOTS', 100))

    if not task_id or not package_id:
        print("Set TASK_OBJECT_ID and PACKAGE_ID in .env")
        sys.exit(1)

    try:
        random_num = run_rng(shots)
        print(f"Random number: {random_num}")
        select_winner_on_sui(random_num, task_id, package_id)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)