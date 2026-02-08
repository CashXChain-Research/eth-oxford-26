# Agent Architecture

Multi-agent orchestration via LangGraph for portfolio optimization.

## Pipeline

Market Agent -> Execution Agent -> Risk Agent -> Approve/Reject

### Market Agent
Gathers and processes market data.
- Fetches price feeds (CoinGecko, Pyth)
- Calculates portfolio metrics
- Analyzes sentiment and trends

### Execution Agent
Runs QUBO optimization on market data.
- Formulates portfolio optimization as QUBO
- Selects solver (D-Wave simulated annealing or scipy)
- Returns optimized weights

### Risk Agent
Pre-flight safety validation before execution.
- Checks spending caps and volume limits
- Verifies slippage protection
- Validates position concentration
- Approves or rejects trade

## Implementation

File: agents/manager.py

Uses LangGraph StateGraph for workflow:
- State: Shared context across agents
- Edges: Directed flow between agents
- Tools: Agent actions (market fetching, optimization, validation)

Example:
```python
from agents.manager import run_pipeline

state = run_pipeline(
    market_data=prices,
    config=portfolio_config,
    dry_run=False
)
print(state.optimization_result.weights)
```

## Data Flow

1. User requests optimization
2. Market Agent fetches prices and calculates metrics
3. Execution Agent runs QUBO solver on metrics
4. Risk Agent validates optimization result
5. If approved: Relayer submits to blockchain
6. If rejected: Return error message

## Safety

All agents enforce guardrails:
- Spending caps: Maximum spend per trade
- Volume limits: Maximum volume per asset
- Concentration limits: Maximum weight per asset
- Slippage protection: Min output validation

Dry-run mode available for simulation without blockchain settlement.

## Integration

Agents are called by api.py endpoint /optimize:
- Receives market symbols and config
- Calls run_pipeline()
- Returns optimized weights or error

Related: blockchain.relayer submits approved trades to Sui.
