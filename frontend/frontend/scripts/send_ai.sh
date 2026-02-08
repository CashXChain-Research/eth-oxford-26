#!/usr/bin/env bash
# send_ai.sh — Simple example: POST to an AI endpoint
# Usage: ./scripts/send_ai.sh
# Requires: curl

set -euo pipefail

URL="https://cashxchain-ai-v1.cashxchain.workers.dev/"
PROMPT=${1:-"Hello"}

PAYLOAD=$(printf '{"prompt":"%s"}' "$PROMPT")

echo "POST $URL"
echo "Payload: $PAYLOAD"
curl -sS -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -o /tmp/ai_response.txt || true

echo "--- raw response ---"
cat /tmp/ai_response.txt || true

# Notes:
# - If your endpoint requires auth, add: -H "Authorization: Bearer <TOKEN>"
