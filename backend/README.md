# Backend

This backend contains:

- `quantum_rng.py`: Python script to generate quantum random numbers using AWS Braket (defaults to SV1 simulator).
- `sui_contract/`: Sui Move smart contract for AI task agent registration and winner selection.
- `integrate.py`: Script to run RNG and call select_winner on the Sui contract (one-shot).
- `relayer.py`: Event listener / Oracle that watches Sui for AgentRegistered events and automatically triggers RNG + select_winner.

## Setup

1. Copy `.env.example` to `.env` and fill in your credentials/keys.
2. Install Python dependencies: `pip install -r requirements.txt`
3. For AWS Braket: Ensure AWS credentials are set (via .env or aws configure).
4. For Sui: Set up Sui CLI, deploy the contract to get PACKAGE_ID and TASK_OBJECT_ID, update .env.

## Usage

### Run quantum RNG (standalone)
```bash
python3 quantum_rng.py --shots 100
```

### Run full integration (one-shot)
```bash
python3 integrate.py
```

### Run relayer (continuous event listener)
```bash
python3 relayer.py
```

The relayer will:
1. Poll Sui RPC for AgentRegistered events
2. Trigger quantum RNG on AWS Braket
3. Call select_winner with the random number

### Deploy Sui contract
```bash
cd sui_contract
sui move build
sui client publish --gas-budget 50000000
```

## Flow

1. User registers an agent on Sui → emits `AgentRegistered` event
2. Relayer sees the event, triggers quantum RNG
3. AWS Braket generates random number
4. Relayer calls `select_winner` on the contract
5. Winner is selected via modulo and `WinnerSelected` event is emitted

- Run quantum RNG: `python3 quantum_rng.py --shots 100`
- Deploy Sui contract: Publish the package on Sui devnet/testnet.