# Claude Code Push Notifications

Receive Claude Code notifications (task completion, permission prompts, idle prompts) on your phone as push notifications. Respond to permission prompts remotely via tmux.

## Architecture

```
Claude Code Hook (stdin JSON)
  → hooks/notify.sh (extracts fields, POSTs via curl)
    → FastAPI server (localhost:8765)
      → pywebpush sends Web Push to all subscribers
        → Phone PWA service worker shows notification
          → [Optional] Approve/Reject → tmux send-keys back to Claude
```

The server runs locally. Use ngrok (or similar) to expose it over HTTPS so your phone can install the PWA and subscribe to push notifications.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [jq](https://jqlang.github.io/jq/) (used by the hook script)
- [ngrok](https://ngrok.com/) (or any HTTPS tunnel, for phone access)
- [tmux](https://github.com/tmux/tmux) (optional, needed for remote approve/reject)

## Setup

### 1. Install dependencies

```bash
cd notify_test
uv sync
```

This installs FastAPI, uvicorn, pywebpush, and python-dotenv into a local `.venv`.

### 2. Start the server

```bash
uv run python -m server.main
```

On first run, this auto-generates a `.env` file containing:
- **VAPID key pair** — used for Web Push encryption
- **API key** — authenticates the hook script's requests to the server

The server prints both keys to the console on startup.

### 3. Configure Claude Code hooks

Add the hook script to your Claude Code settings (`~/.claude/settings.json`):

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/absolute/path/to/notify_test/hooks/notify.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "/absolute/path/to/notify_test/hooks/notify.sh",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Replace `/absolute/path/to` with the actual path to your `notify_test` directory.

### 4. Expose with ngrok

```bash
ngrok http 8765
```

Copy the `https://...ngrok-free.app` URL — you'll open this on your phone.

### 5. Subscribe on your phone

1. Open the ngrok URL on your phone's browser
2. **iOS only:** tap Share → "Add to Home Screen", then open the installed app
3. Tap **Enable Notifications** and accept the browser permission prompt

You're now receiving push notifications.

## Usage

### Automatic (via Claude Code)

Once the hooks are configured, notifications are sent automatically when:
- **Stop** — Claude finishes a task
- **Notification** — Claude needs permission or is idle

### Manual test

```bash
# From the server machine:
API_KEY=$(grep '^API_KEY=' .env | cut -d'=' -f2)

curl -X POST http://localhost:8765/api/notify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"event_type":"Stop","title":"Test","message":"Hello from curl"}'
```

Or use the **Send Test Notification** button in the PWA after subscribing.

### Hook script test

```bash
echo '{"hook_event_name":"Stop","cwd":"/tmp/my-project","session_id":"x"}' \
  | ./hooks/notify.sh
```

## Remote Approve/Reject (tmux)

If Claude Code is running inside a tmux session, you can respond to permission prompts directly from your phone:

- **Approve** — sends `y` to the tmux pane
- **Reject** — sends `Escape` to the tmux pane
- **Text input** — sends arbitrary text + Enter (for idle prompts)

The hook script automatically captures the `$TMUX_PANE` environment variable. No extra configuration needed — just run Claude Code inside tmux.

Action buttons appear both on the push notification itself (Android) and in the PWA's notification history.

## API Endpoints

| Endpoint | Method | Auth | Purpose |
|---|---|---|---|
| `/` | GET | — | PWA shell |
| `/api/vapid-public-key` | GET | — | VAPID public key for browser subscribe |
| `/api/subscribe` | POST | — | Store push subscription |
| `/api/unsubscribe` | POST | — | Remove push subscription |
| `/api/notify` | POST | API key | Webhook from hooks → push to all subscribers |
| `/api/test-notify` | POST | — | Send a test push notification |
| `/api/respond` | POST | — | Send keystrokes to tmux pane |
| `/api/notifications` | GET | — | Recent notification history |

## File Structure

```
notify_test/
├── pyproject.toml          # Project config + dependencies
├── .env                    # Auto-generated VAPID keys + API key (gitignored)
├── .gitignore
├── server/
│   ├── __init__.py
│   ├── main.py             # FastAPI app + all routes
│   ├── config.py           # Loads .env, auto-generates VAPID keys on first run
│   ├── push.py             # pywebpush wrapper, sends to all subscribers
│   └── store.py            # JSON file storage for subscriptions + history
├── static/
│   ├── index.html          # PWA shell
│   ├── manifest.json       # Web App Manifest
│   ├── sw.js               # Service Worker (push display + action buttons)
│   ├── app.js              # Subscription management + notification UI
│   ├── style.css           # Dark theme, mobile-first
│   ├── icon-192.svg        # App icon
│   └── icon-512.svg        # App icon
├── hooks/
│   └── notify.sh           # Claude Code hook script
└── data/                   # Runtime data (gitignored)
    ├── subscriptions.json
    └── notifications.json
```

## Troubleshooting

**No notifications on iOS?**
iOS requires the PWA to be installed to the home screen before push notifications work. Open via the installed app icon, not the browser.

**Hook not firing?**
Check that the path in `settings.json` is absolute and the script is executable (`chmod +x hooks/notify.sh`).

**`tmux send-keys` failing?**
Make sure Claude Code is running inside a tmux session. The `$TMUX_PANE` variable must be set in the hook's environment.

**Server not reachable from phone?**
Ensure ngrok is running and pointing to port 8765. The phone must access the `https://` ngrok URL, not `localhost`.
