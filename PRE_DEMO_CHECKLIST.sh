#!/bin/bash

# Pre-Demo Checklist - CashXChain Quantum Vault
# ETH Oxford 2026

echo "Pre-Demo Checklist"
echo "=================="
echo ""

cd /home/korbi/Dokumente/eth-oxford-26 || exit 1

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

check_count=0
pass_count=0

check() {
    local title=$1
    local command=$2
    
    check_count=$((check_count + 1))
    echo -n "  [$check_count] $title ... "
    
    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        pass_count=$((pass_count + 1))
    else
        echo -e "${RED}FAIL${NC}"
    fi
}

echo "Backend Structure"
echo "-----------------"
check "api.py exists" "[ -f backend/api.py ]"
check "agents/manager.py exists" "[ -f backend/agents/manager.py ]"
check "quantum/optimizer.py exists" "[ -f backend/quantum/optimizer.py ]"
check "blockchain/client.py exists" "[ -f backend/blockchain/client.py ]"
check "core/error_map.py exists" "[ -f backend/core/error_map.py ]"
check "tests/backtester.py exists" "[ -f backend/tests/backtester.py ]"

echo ""
echo "Documentation"
echo "--------------"
check "README.md exists" "[ -f README.md ]"
check "ARCHITECTURE.md exists" "[ -f ARCHITECTURE.md ]"
check "STATUS.md exists" "[ -f STATUS.md ]"
check "backend/README.md exists" "[ -f backend/README.md ]"
check "docs/agents.md exists" "[ -f docs/agents.md ]"

echo ""
echo "Dependencies"
echo "-------------"
check "Python 3 installed" "which python3"
check "requirements.txt exists" "[ -f backend/requirements.txt ]"

echo ""
echo "Services"
echo "--------"
echo "  Terminal 1: uvicorn blockchain.relayer_server:app --port 3001"
echo "  Terminal 2: python3 -m blockchain.event_provider"
echo "  Terminal 3: python3 -m blockchain.relayer"

echo ""
echo "Tests"
echo "-----"
check "pytest available" "which pytest"

echo ""
echo "Result: $pass_count/$check_count checks passed"

if [ $pass_count -eq $check_count ]; then
    echo "Status: READY FOR DEMO"
    exit 0
else
    echo "Status: MISSING ITEMS"
    exit 1
fi
