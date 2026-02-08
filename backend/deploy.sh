#!/usr/bin/env bash
#
# deploy.sh – Build & publish the quantum_vault package to Sui Testnet/Devnet.
#
# Usage:
#   ./deploy.sh              # publish to active env (devnet/testnet)
#   ./deploy.sh --devnet     # force devnet
#   ./deploy.sh --testnet    # force testnet
#
# After a successful publish the script prints the values you need
# for your backend .env file.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONTRACT_DIR="$SCRIPT_DIR/sui_contract"
ENV_FILE="$SCRIPT_DIR/.env"

# ── Helpers ──────────────────────────────────────────────────
red()   { printf '\033[0;31m%s\033[0m\n' "$*"; }
green() { printf '\033[0;32m%s\033[0m\n' "$*"; }
blue()  { printf '\033[0;34m%s\033[0m\n' "$*"; }

# ── Pre-flight checks ───────────────────────────────────────
if ! command -v sui &>/dev/null; then
    red "ERROR: sui CLI not found."
    echo "Install it first:"
    echo "  cargo install --locked --git https://github.com/MystenLabs/sui.git --branch testnet sui"
    echo "  OR download a pre-built binary from https://github.com/MystenLabs/sui/releases"
    exit 1
fi

# ── Optional: switch environment ─────────────────────────────
case "${1:-}" in
    --devnet)
        blue "Switching to devnet..."
        sui client new-env --alias devnet --rpc https://fullnode.devnet.sui.io:443 2>/dev/null || true
        sui client switch --env devnet
        ;;
    --testnet)
        blue "Switching to testnet..."
        sui client new-env --alias testnet --rpc https://fullnode.testnet.sui.io:443 2>/dev/null || true
        sui client switch --env testnet
        ;;
esac

# ── Show active address ─────────────────────────────────────
ADDR=$(sui client active-address)
blue "Active address: $ADDR"
blue "Active environment: $(sui client active-env)"

# ── Request faucet (devnet/testnet only) ─────────────────────
blue "Requesting faucet tokens..."
sui client faucet 2>/dev/null || echo "(faucet may not be available)"

# ── Build ────────────────────────────────────────────────────
blue "Building Move package..."
cd "$CONTRACT_DIR"
sui move build

# ── Publish ──────────────────────────────────────────────────
blue "Publishing package..."
PUBLISH_OUTPUT=$(sui client publish --gas-budget 100000000 --json 2>&1)

# ── Parse output ─────────────────────────────────────────────
PACKAGE_ID=$(echo "$PUBLISH_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for change in data.get('objectChanges', []):
    if change.get('type') == 'published':
        print(change['packageId'])
        break
" 2>/dev/null || echo "PARSE_FAILED")

if [ "$PACKAGE_ID" = "PARSE_FAILED" ] || [ -z "$PACKAGE_ID" ]; then
    red "Could not parse PACKAGE_ID from publish output."
    echo "Raw output:"
    echo "$PUBLISH_OUTPUT"
    exit 1
fi

green " PACKAGE_ID = $PACKAGE_ID"

# ── Find created objects ─────────────────────────────────────
OBJECTS=$(echo "$PUBLISH_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for change in data.get('objectChanges', []):
    if change.get('type') == 'created':
        obj_type = change.get('objectType', '')
        obj_id = change.get('objectId', '')
        print(f'{obj_type} -> {obj_id}')
" 2>/dev/null || echo "")

echo ""
blue "Created objects:"
echo "$OBJECTS"
echo ""

# Extract specific IDs
TASK_OBJECT_ID=$(echo "$PUBLISH_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for change in data.get('objectChanges', []):
    if change.get('type') == 'created' and 'Task' in change.get('objectType', ''):
        print(change['objectId']); break
" 2>/dev/null || echo "")

PORTFOLIO_OBJECT_ID=$(echo "$PUBLISH_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for change in data.get('objectChanges', []):
    if change.get('type') == 'created' and 'Portfolio' in change.get('objectType', ''):
        print(change['objectId']); break
" 2>/dev/null || echo "")

ADMIN_CAP_ID=$(echo "$PUBLISH_OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for change in data.get('objectChanges', []):
    if change.get('type') == 'created' and 'AdminCap' in change.get('objectType', ''):
        print(change['objectId']); break
" 2>/dev/null || echo "")

green " TASK_OBJECT_ID    = $TASK_OBJECT_ID"
green " PORTFOLIO_OBJ_ID  = $PORTFOLIO_OBJECT_ID"
green " ADMIN_CAP_ID      = $ADMIN_CAP_ID"

# ── Update .env ──────────────────────────────────────────────
if [ -f "$ENV_FILE" ]; then
    blue "Updating $ENV_FILE ..."
    sed -i "s|^PACKAGE_ID=.*|PACKAGE_ID=$PACKAGE_ID|" "$ENV_FILE"
    sed -i "s|^TASK_OBJECT_ID=.*|TASK_OBJECT_ID=$TASK_OBJECT_ID|" "$ENV_FILE"

    # Ensure all keys exist, then update
    grep -q '^PORTFOLIO_OBJECT_ID=' "$ENV_FILE" || echo "PORTFOLIO_OBJECT_ID=" >> "$ENV_FILE"
    grep -q '^PORTFOLIO_ID=' "$ENV_FILE"        || echo "PORTFOLIO_ID=" >> "$ENV_FILE"
    grep -q '^ADMIN_CAP_ID=' "$ENV_FILE"        || echo "ADMIN_CAP_ID=" >> "$ENV_FILE"

    sed -i "s|^PORTFOLIO_OBJECT_ID=.*|PORTFOLIO_OBJECT_ID=$PORTFOLIO_OBJECT_ID|" "$ENV_FILE"
    sed -i "s|^PORTFOLIO_ID=.*|PORTFOLIO_ID=$PORTFOLIO_OBJECT_ID|" "$ENV_FILE"
    sed -i "s|^ADMIN_CAP_ID=.*|ADMIN_CAP_ID=$ADMIN_CAP_ID|" "$ENV_FILE"
    green " .env updated!"
else
    blue "No .env found, creating one..."
    cat > "$ENV_FILE" <<EOF
PACKAGE_ID=$PACKAGE_ID
TASK_OBJECT_ID=$TASK_OBJECT_ID
PORTFOLIO_OBJECT_ID=$PORTFOLIO_OBJECT_ID
ADMIN_CAP_ID=$ADMIN_CAP_ID
SUI_RPC_URL=https://fullnode.devnet.sui.io:443
SHOTS=100
POLL_INTERVAL=5
EOF
    green " .env created!"
fi

# ── Update config.json ───────────────────────────────────────────────────
CONFIG_FILE="$SCRIPT_DIR/../config.json"
if [ -f "$CONFIG_FILE" ]; then
    blue "Updating config.json ..."
    python3 -c "
import json, sys
with open('$CONFIG_FILE', 'r') as f:
    cfg = json.load(f)
cfg['package_id'] = '$PACKAGE_ID'
cfg['objects']['portfolio_id'] = '${PORTFOLIO_OBJECT_ID}'
cfg['objects']['admin_cap_id'] = '$ADMIN_CAP_ID'
with open('$CONFIG_FILE', 'w') as f:
    json.dump(cfg, f, indent=2)
" 2>/dev/null && green " config.json updated!" || echo "(config.json update skipped)"
fi

echo ""
green "════════════════════════════════════════════"
green "  quantum_vault deployed!"
green "  PACKAGE_ID        = $PACKAGE_ID"
green "  ADMIN_CAP_ID      = $ADMIN_CAP_ID"
green "  PORTFOLIO_ID      = $PORTFOLIO_OBJECT_ID"
green "════════════════════════════════════════════"
echo ""
blue "Next steps:"
echo ""
echo "  1. Issue AgentCap for Valentin (bound to this Portfolio):"
echo "     sui client call --package $PACKAGE_ID --module agent_registry \\"
echo "       --function issue_agent_cap \\"
echo "       --args $ADMIN_CAP_ID <VALENTIN_WALLET> 'Agent_V1' $PORTFOLIO_OBJECT_ID \\"
echo "       --gas-budget 10000000"
echo ""
echo "     Then add the AGENT_CAP_ID from the output to .env + config.json"
echo ""
echo "  2. Deposit SUI into the vault:"
echo "     sui client call --package $PACKAGE_ID --module portfolio \\"
echo "       --function deposit \\"
echo "       --args $ADMIN_CAP_ID $PORTFOLIO_OBJECT_ID <COIN_OBJECT_ID> \\"
echo "       --gas-budget 10000000"
echo ""
echo "  3. Valentin calls portfolio::execute_rebalance with his AgentCap"
echo "     (see frontend/frontend/constants.ts for all function targets)"
