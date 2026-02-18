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
TRANSCRIPT=$(echo "$INPUT" | jq -r '.transcript_path // empty')
NOTIFICATION_TYPE=$(echo "$INPUT" | jq -r '.notification_type // empty')

# Extract project name from cwd
PROJECT=$(basename "${CWD:-unknown}")

# Extract context from transcript (last assistant message with tool use or text)
CONTEXT=""
if [[ -n "$TRANSCRIPT" && -f "$TRANSCRIPT" ]]; then
  # Get the last few lines and extract the most recent tool call or assistant text
  CONTEXT=$(tail -20 "$TRANSCRIPT" | jq -r '
    select(.type == "assistant") |
    .message.content[]? |
    if .type == "tool_use" then
      "Tool: \(.name)\(.input | if .command then " — \(.command)" elif .file_path then " — \(.file_path)" elif .pattern then " — \(.pattern)" else "" end)"
    elif .type == "text" then
      .text
    else empty end
  ' 2>/dev/null | tail -3 | head -c 500 || true)
fi

# Build title and message based on event type
case "$EVENT" in
  Stop)
    TITLE="$PROJECT — Done"
    # Try to get the last assistant text as a summary
    if [[ -n "$CONTEXT" ]]; then
      MESSAGE="$CONTEXT"
    else
      MESSAGE="Task completed"
    fi
    ;;
  Notification)
    TITLE=$(echo "$INPUT" | jq -r '.title // "Claude Code"')
    MESSAGE=$(echo "$INPUT" | jq -r '.message // ""')
    # Append context for permission prompts
    if [[ "$NOTIFICATION_TYPE" == "permission_prompt" && -n "$CONTEXT" ]]; then
      MESSAGE="${MESSAGE}
${CONTEXT}"
    fi
    # Prepend project name
    TITLE="$PROJECT — $TITLE"
    ;;
  *)
    TITLE="$PROJECT — $EVENT"
    MESSAGE="${CONTEXT:-Event: $EVENT}"
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
