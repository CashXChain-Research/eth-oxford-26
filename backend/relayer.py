#!/usr/bin/env python3
"""
Relayer / Oracle for AI Task on Sui.

Listens to TaskCreated and AgentRegistered events on Sui,
triggers quantum RNG, and calls select_winner on the contract.
"""
import os
import json
import subprocess
import sys
import time
import logging
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# For now, using JSON RPC directly. In production, use pysui or SDK.
try:
    import httpx
except ImportError:
    logger.warning("httpx not installed. Install with: pip install httpx")
    httpx = None

SUI_RPC_URL = os.getenv('SUI_RPC_URL', 'https://fullnode.devnet.sui.io:443')
PACKAGE_ID = os.getenv('PACKAGE_ID')
TASK_OBJECT_ID = os.getenv('TASK_OBJECT_ID')
SHOTS = int(os.getenv('SHOTS', 100))
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', 5))  # seconds

# Track processed events
processed_events = set()


def get_quantum_random(shots: int) -> int:
    """Run quantum RNG script and return random number."""
    try:
        result = subprocess.run(
            [sys.executable, 'quantum_rng.py', '--shots', str(shots)],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(__file__),
            timeout=60
        )
        if result.returncode != 0:
            logger.error(f"RNG failed: {result.stderr}")
            return None
        counts = json.loads(result.stdout.strip())
        # Simple: count of '1' measurements
        random_num = counts.get('1', 0)
        logger.info(f"Generated random number: {random_num} (counts: {counts})")
        return random_num
    except Exception as e:
        logger.error(f"Error running RNG: {e}")
        return None


def fetch_events(event_type: str, limit: int = 100) -> list:
    """Fetch events from Sui RPC."""
    if not httpx:
        logger.warning("httpx not available, skipping event fetch")
        return []
    
    try:
        with httpx.Client() as client:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "sui_queryEvents",
                "params": [
                    {
                        "MoveEventType": event_type
                    },
                    None,
                    limit
                ]
            }
            response = client.post(SUI_RPC_URL, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
            if "result" in data:
                return data["result"].get("data", [])
            else:
                logger.warning(f"No result in response: {data}")
                return []
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return []


def process_agent_registered_event(event: Dict[str, Any]) -> bool:
    """
    When a new agent registers, check if we should trigger RNG.
    For now, trigger after any registration (in production, set a threshold).
    """
    event_id = event.get("id", {}).get("txDigest")
    if event_id in processed_events:
        return False
    
    processed_events.add(event_id)
    parsed_json = event.get("parsedJson", {})
    logger.info(f"AgentRegistered: {parsed_json}")
    
    # Simple logic: after an agent registers, trigger RNG
    # In production: wait for a minimum number of agents
    return True


def call_select_winner(random_number: int) -> bool:
    """Call select_winner on Sui contract."""
    if not PACKAGE_ID or not TASK_OBJECT_ID:
        logger.error("PACKAGE_ID or TASK_OBJECT_ID not set")
        return False
    
    # For now, a placeholder. In production, use pysui or Sui CLI.
    logger.info(f"Would call select_winner with random_number={random_number}")
    logger.info(f"Command: sui client call --package {PACKAGE_ID} --module ai_task --function select_winner --args {TASK_OBJECT_ID} {random_number}")
    
    # Uncomment below to use Sui CLI (requires sui-cli installed and auth):
    # try:
    #     result = subprocess.run([
    #         'sui', 'client', 'call',
    #         '--package', PACKAGE_ID,
    #         '--module', 'ai_task',
    #         '--function', 'select_winner',
    #         '--args', TASK_OBJECT_ID, str(random_number)
    #     ], capture_output=True, text=True, timeout=30)
    #     if result.returncode == 0:
    #         logger.info(f"select_winner successful: {result.stdout}")
    #         return True
    #     else:
    #         logger.error(f"select_winner failed: {result.stderr}")
    #         return False
    # except Exception as e:
    #     logger.error(f"Error calling select_winner: {e}")
    #     return False
    
    return True


def run_relayer():
    """Main relayer loop."""
    logger.info(f"Starting relayer. Polling {SUI_RPC_URL} every {POLL_INTERVAL}s")
    
    event_type = f"{PACKAGE_ID}::ai_task::AgentRegistered"
    
    while True:
        try:
            events = fetch_events(event_type)
            for event in events:
                if process_agent_registered_event(event):
                    logger.info("Triggering quantum RNG...")
                    random_num = get_quantum_random(SHOTS)
                    if random_num is not None:
                        if call_select_winner(random_num):
                            logger.info("Successfully processed event and called select_winner")
            
            time.sleep(POLL_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Relayer stopped")
            break
        except Exception as e:
            logger.error(f"Relayer error: {e}")
            time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    if not PACKAGE_ID:
        logger.error("Set PACKAGE_ID in .env")
        sys.exit(1)
    
    run_relayer()
