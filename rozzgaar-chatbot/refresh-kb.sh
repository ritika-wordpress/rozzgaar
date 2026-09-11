#!/usr/bin/env bash
set -euo pipefail
APP_DIR="$HOME/rozzgaar-chatbot/rozzgaar-chatbot"
ENV_FILE="$APP_DIR/.env"
STATE_FILE="$HOME/.kb-refresh-state"
BACKEND_URL="https://api.rozzgaar.in"
ADMIN_SECRET=$(grep -E '^ADMIN_SECRET=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"')
RESPONSE=$(curl -sf -X POST "$BACKEND_URL/ingest/refresh" -H "X-Admin-Secret: $ADMIN_SECRET") || { echo "$(date -Iseconds) ERROR: refresh request failed"; exit 1; }
NEW_STATE=$(echo "$RESPONSE" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d['courses_indexed']},{d['bundles_indexed']},{d['pages_indexed']},{d['chunks_indexed']}\")")
OLD_STATE=""
[ -f "$STATE_FILE" ] && OLD_STATE=$(cat "$STATE_FILE")
if [ "$NEW_STATE" == "$OLD_STATE" ]; then
  echo "$(date -Iseconds) No change detected. ($NEW_STATE)"
else
  echo "$(date -Iseconds) CHANGE DETECTED - old: [$OLD_STATE] new: [$NEW_STATE]"
  echo "$NEW_STATE" > "$STATE_FILE"
fi
