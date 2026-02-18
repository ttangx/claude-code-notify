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


# Static files (CSS, JS, etc.) — mounted last so API routes take priority
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    print(f"VAPID public key: {VAPID_PUBLIC_KEY}")
    print(f"API key: {API_KEY}")
    uvicorn.run(app, host="0.0.0.0", port=8765)
