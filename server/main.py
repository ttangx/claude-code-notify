import os
import re
import subprocess
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.config import VAPID_PUBLIC_KEY, API_KEY
from server import store, push

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI()


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/sw.js")
async def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/manifest.json")
async def manifest():
    return FileResponse(STATIC_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/api/vapid-public-key")
async def vapid_public_key():
    return {"publicKey": VAPID_PUBLIC_KEY}


@app.post("/api/subscribe")
async def subscribe(request: Request):
    sub = await request.json()
    if not sub.get("endpoint"):
        raise HTTPException(400, "Missing endpoint")
    store.add_subscription(sub)
    return {"ok": True}


@app.post("/api/unsubscribe")
async def unsubscribe(request: Request):
    body = await request.json()
    endpoint = body.get("endpoint", "")
    removed = store.remove_subscription(endpoint)
    return {"ok": True, "removed": removed}


@app.post("/api/notify")
async def notify(request: Request, x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(403, "Invalid API key")

    body = await request.json()
    title = body.get("title", "Claude Code")
    message = body.get("message", "")
    event_type = body.get("event_type", "")
    tmux_pane = body.get("tmux_pane", "")
    session_id = body.get("session_id", "")

    nid = store.add_notification({
        "title": title,
        "message": message,
        "event_type": event_type,
        "tmux_pane": tmux_pane,
        "session_id": session_id,
    })

    # Include notification id and whether it's actionable in the push payload
    actionable = event_type == "Notification" and bool(tmux_pane)
    sent = push.send_push_to_all(
        title=title,
        body=message,
        data={"event_type": event_type, "notification_id": nid, "actionable": actionable},
    )
    return {"ok": True, "sent_to": sent, "notification_id": nid}


VALID_TMUX_PANE = re.compile(r"^%\d+$")


@app.post("/api/respond")
async def respond(request: Request):
    """Send keystrokes to the tmux pane associated with a notification."""
    body = await request.json()
    nid = body.get("notification_id", "")
    action = body.get("action", "")

    if action not in ("approve", "reject", "text"):
        raise HTTPException(400, "action must be 'approve', 'reject', or 'text'")

    notification = store.get_notification(nid)
    if not notification:
        raise HTTPException(404, "Notification not found")

    tmux_pane = notification.get("tmux_pane", "")
    if not tmux_pane or not VALID_TMUX_PANE.match(tmux_pane):
        raise HTTPException(400, "No valid tmux pane for this notification")

    if notification.get("responded"):
        raise HTTPException(409, "Already responded to this notification")

    # Determine keys to send
    if action == "approve":
        keys = ["y"]
    elif action == "reject":
        keys = ["Escape"]
    else:
        # action == "text": send arbitrary text (for responding to idle prompts)
        text = body.get("text", "")
        if not text:
            raise HTTPException(400, "text field required for text action")
        keys = [text, "Enter"]

    try:
        for key in keys:
            subprocess.run(
                ["tmux", "send-keys", "-t", tmux_pane, key],
                check=True,
                capture_output=True,
                timeout=5,
            )
    except FileNotFoundError:
        raise HTTPException(500, "tmux not found on server")
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"tmux send-keys failed: {e.stderr.decode()}")

    store.update_notification(nid, {"responded": action})
    return {"ok": True, "action": action, "tmux_pane": tmux_pane}


@app.post("/api/test-notify")
async def test_notify():
    """Send a test notification (no API key needed — for PWA UI button)."""
    title = "Test Notification"
    message = "If you see this, push notifications are working!"
    store.add_notification({"title": title, "message": message, "event_type": "test"})
    sent = push.send_push_to_all(title=title, body=message, data={"event_type": "test"})
    return {"ok": True, "sent_to": sent}


@app.get("/api/notifications")
async def notifications():
    return store.get_notifications()


# --- Session management ---

VALID_SESSION_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


@app.get("/api/directories")
async def directories():
    return store.get_directories()


@app.get("/api/sessions")
async def list_sessions():
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}|#{session_created}|#{session_path}|#{session_windows}"],
            capture_output=True, text=True, timeout=5,
        )
    except FileNotFoundError:
        raise HTTPException(500, "tmux not found on server")
    except subprocess.TimeoutExpired:
        raise HTTPException(500, "tmux timed out")

    if result.returncode != 0:
        # No sessions running returns exit code 1
        return []

    sessions = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("|", 3)
        if len(parts) == 4:
            sessions.append({
                "name": parts[0],
                "created": int(parts[1]) if parts[1].isdigit() else 0,
                "path": parts[2],
                "windows": int(parts[3]) if parts[3].isdigit() else 1,
            })
    return sessions


@app.post("/api/sessions")
async def create_session(request: Request):
    body = await request.json()
    path = body.get("path", "")

    if not path:
        raise HTTPException(400, "Missing path")

    # Validate path is in the configured directories
    dirs = store.get_directories()
    allowed_paths = {d["path"] for d in dirs}
    if path not in allowed_paths:
        raise HTTPException(403, "Path not in configured directories")

    target = Path(path)
    if not target.is_dir():
        raise HTTPException(400, "Path does not exist or is not a directory")

    name = target.name
    if not VALID_SESSION_NAME.match(name):
        raise HTTPException(400, "Directory name contains invalid characters for a tmux session name")

    try:
        # Strip CLAUDECODE env var so claude doesn't think it's nested
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        subprocess.run(
            ["tmux", "new-session", "-d", "-s", name, "-c", str(target)],
            check=True, capture_output=True, timeout=5, env=env,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", name, "claude", "Enter"],
            check=True, capture_output=True, timeout=5,
        )
    except FileNotFoundError:
        raise HTTPException(500, "tmux not found on server")
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"tmux error: {e.stderr.decode()}")

    return {"ok": True, "name": name, "path": str(target)}


@app.post("/api/sessions/kill")
async def kill_session(request: Request):
    body = await request.json()
    name = body.get("name", "")

    if not name or not VALID_SESSION_NAME.match(name):
        raise HTTPException(400, "Invalid session name")

    try:
        subprocess.run(
            ["tmux", "kill-session", "-t", name],
            check=True, capture_output=True, timeout=5,
        )
    except FileNotFoundError:
        raise HTTPException(500, "tmux not found on server")
    except subprocess.CalledProcessError as e:
        raise HTTPException(500, f"tmux error: {e.stderr.decode()}")

    return {"ok": True, "killed": name}


# Static files (CSS, JS, etc.) — mounted last so API routes take priority
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    print(f"VAPID public key: {VAPID_PUBLIC_KEY}")
    print(f"API key: {API_KEY}")
    uvicorn.run(app, host="0.0.0.0", port=8765)
