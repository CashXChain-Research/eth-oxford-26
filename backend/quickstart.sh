#!/bin/bash
# Quick Start Backend

set -e

echo "================================"
echo "Backend Startup Guide"
echo "================================"
echo ""

# Step 1: Virtual Environment
echo "Step 1: Python Virtual Environment"
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo "  ✓ Activated .venv"
echo ""

# Step 2: Dependencies
echo "Step 2: Install Dependencies"
if [ -f "requirements.txt" ]; then
    pip install -q -r requirements.txt
    echo "  ✓ Dependencies installed"
else
    echo "  ✗ requirements.txt not found"
    exit 1
fi
echo ""

# Step 3: Environment Configuration
echo "Step 3: Environment Setup"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo "  ✓ Created .env from template"
        echo "  NOTE: Edit .env to add your Sui credentials:"
        echo "    - SUI_NETWORK (devnet/testnet/mainnet)"
        echo "    - SUI_PRIVATE_KEY"
        echo "    - PACKAGE_ID"
        echo "    - PORTFOLIO_OBJECT_ID"
    fi
else
    echo "  ✓ .env exists"
fi
echo ""

# Step 4: Verify Imports
echo "Step 4: Verify Imports"
python3 -c "
import sys
modules = [
    'agents.manager',
    'quantum.optimizer',
    'blockchain.client',
    'core.error_map',
    'tests.integration_tests',
]
ok = sum(1 for m in modules if __import__(m))
print(f'  ✓ {ok}/{len(modules)} core modules importable')
sys.exit(0 if ok == len(modules) else 1)
" || exit 1
echo ""

# Step 5: Available Commands
echo "Step 5: Start Services"
echo ""
echo "API Server (port 3001):"
echo "  uvicorn api:app --port 3001"
echo ""
echo "Event Provider (port 3002):"
echo "  python3 -m blockchain.event_provider"
echo ""
echo "Async Relayer:"
echo "  python3 -m blockchain.relayer"
echo ""
echo "CLI Commands:"
echo "  python3 -m blockchain.agent_executor demo [amount]"
echo "  python3 -m blockchain.agent_executor dryrun [amount]"
echo ""
echo "Tests:"
echo "  pytest tests/"
echo "  python3 -m tests.safety_tests"
echo "  python3 -m tests.integration_tests"
echo ""
echo "================================"
echo "Ready to run!"
echo "================================"
