#!/usr/bin/env bash
# Claude Code hook: sends push notifications via the local notify server.
# Reads hook JSON from stdin. Never blocks Claude (curl has --max-time 5, || true).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

# Load API key from .env
if [[ ! -f "$ENV_FILE" ]]; then
  exit 0
fi
API_KEY=$(grep '^API_KEY=' "$ENV_FILE" | cut -d'=' -f2)
if [[ -z "$API_KEY" ]]; then
  exit 0
fi

SERVER="http://localhost:8765"

# Read JSON from stdin
INPUT=$(cat)

EVENT=$(echo "$INPUT" | jq -r '.hook_event_name // empty')
CWD=$(echo "$INPUT" | jq -r '.cwd // empty')
SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')

# Extract project name from cwd
PROJECT=$(basename "${CWD:-unknown}")

# Build title and message based on event type
case "$EVENT" in
  Stop)
    TITLE="Claude Code - $PROJECT"
    MESSAGE="Task completed"
    ;;
  Notification)
    # Notification events have a title and message in the hook data
    TITLE=$(echo "$INPUT" | jq -r '.title // "Claude Code"')
    MESSAGE=$(echo "$INPUT" | jq -r '.message // ""')
    # If title is generic, prepend project name
    if [[ "$TITLE" == "Claude Code" ]]; then
      TITLE="Claude Code - $PROJECT"
    fi
    ;;
  *)
    TITLE="Claude Code - $PROJECT"
    MESSAGE="Event: $EVENT"
    ;;
esac

# Capture tmux pane for remote response capability
TMUX_TARGET="${TMUX_PANE:-}"

# Send to local notification server (never block Claude)
curl -s -X POST "$SERVER/api/notify" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "$(jq -n \
    --arg event_type "$EVENT" \
    --arg title "$TITLE" \
    --arg message "$MESSAGE" \
    --arg tmux_pane "$TMUX_TARGET" \
    --arg session_id "$SESSION_ID" \
    '{event_type: $event_type, title: $title, message: $message, tmux_pane: $tmux_pane, session_id: $session_id}')" \
  --max-time 5 || true
