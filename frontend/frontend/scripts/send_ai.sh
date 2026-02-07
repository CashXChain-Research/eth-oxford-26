#!/usr/bin/env bash
# send_ai.sh — Einfaches Beispiel: POST an AI-Endpoint
# Nutzung: ./scripts/send_ai.sh
# Erwartet: curl installiert

set -euo pipefail

URL="https://cashxchain-ai-v1.cashxchain.workers.dev/"
PROMPT=${1:-"Hallo"}

PAYLOAD=$(printf '{"prompt":"%s"}' "$PROMPT")

echo "POST $URL"
echo "Payload: $PAYLOAD"
curl -sS -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -o /tmp/ai_response.txt || true

echo "--- raw response ---"
cat /tmp/ai_response.txt || true

# Hinweis:
# - Wenn dein Endpoint Auth benötigt, füge: -H "Authorization: Bearer <TOKEN>"
