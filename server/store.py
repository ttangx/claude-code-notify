import json
import time
import uuid
from pathlib import Path
from threading import Lock

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUBS_FILE = DATA_DIR / "subscriptions.json"
HISTORY_FILE = DATA_DIR / "notifications.json"
MAX_HISTORY = 100

_lock = Lock()


def _ensure_data_dir():
    DATA_DIR.mkdir(exist_ok=True)


def _read_json(path: Path) -> list:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _write_json(path: Path, data: list):
    path.write_text(json.dumps(data, indent=2))


def get_subscriptions() -> list[dict]:
    _ensure_data_dir()
    with _lock:
        return _read_json(SUBS_FILE)


def add_subscription(sub: dict):
    _ensure_data_dir()
    with _lock:
        subs = _read_json(SUBS_FILE)
        # Replace if same endpoint exists
        subs = [s for s in subs if s.get("endpoint") != sub.get("endpoint")]
        subs.append(sub)
        _write_json(SUBS_FILE, subs)


def remove_subscription(endpoint: str) -> bool:
    _ensure_data_dir()
    with _lock:
        subs = _read_json(SUBS_FILE)
        new_subs = [s for s in subs if s.get("endpoint") != endpoint]
        removed = len(new_subs) < len(subs)
        _write_json(SUBS_FILE, new_subs)
        return removed


def add_notification(notification: dict) -> str:
    _ensure_data_dir()
    nid = uuid.uuid4().hex[:12]
    notification["id"] = nid
    notification["timestamp"] = time.time()
    with _lock:
        history = _read_json(HISTORY_FILE)
        history.insert(0, notification)
        history = history[:MAX_HISTORY]
        _write_json(HISTORY_FILE, history)
    return nid


def get_notification(nid: str) -> dict | None:
    _ensure_data_dir()
    with _lock:
        history = _read_json(HISTORY_FILE)
        for n in history:
            if n.get("id") == nid:
                return n
    return None


def update_notification(nid: str, updates: dict):
    _ensure_data_dir()
    with _lock:
        history = _read_json(HISTORY_FILE)
        for n in history:
            if n.get("id") == nid:
                n.update(updates)
                break
        _write_json(HISTORY_FILE, history)


def get_notifications(limit: int = 50) -> list[dict]:
    _ensure_data_dir()
    with _lock:
        history = _read_json(HISTORY_FILE)
        return history[:limit]
