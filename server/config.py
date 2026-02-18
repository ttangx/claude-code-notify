import base64
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from py_vapid import Vapid


ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _generate_vapid_keys() -> tuple[str, str]:
    """Generate VAPID key pair, return (private_b64url, public_b64url)."""
    vapid = Vapid()
    vapid.generate_keys()
    raw_private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = vapid.public_key.public_bytes(
        encoding=__import__("cryptography").hazmat.primitives.serialization.Encoding.X962,
        format=__import__("cryptography").hazmat.primitives.serialization.PublicFormat.UncompressedPoint,
    )
    private_b64 = base64.urlsafe_b64encode(raw_private).rstrip(b"=").decode()
    public_b64 = base64.urlsafe_b64encode(raw_public).rstrip(b"=").decode()
    return private_b64, public_b64


def _ensure_env():
    """Create .env with VAPID keys and API key if it doesn't exist."""
    if ENV_PATH.exists():
        return
    private_key, public_key = _generate_vapid_keys()
    api_key = secrets.token_urlsafe(32)
    ENV_PATH.write_text(
        f"VAPID_PRIVATE_KEY={private_key}\n"
        f"VAPID_PUBLIC_KEY={public_key}\n"
        f"VAPID_CLAIM_EMAIL=mailto:admin@example.com\n"
        f"API_KEY={api_key}\n"
    )
    print(f"Generated .env with new VAPID keys and API key")


_ensure_env()
load_dotenv(ENV_PATH)

VAPID_PRIVATE_KEY: str = os.environ["VAPID_PRIVATE_KEY"]
VAPID_PUBLIC_KEY: str = os.environ["VAPID_PUBLIC_KEY"]
VAPID_CLAIM_EMAIL: str = os.environ["VAPID_CLAIM_EMAIL"]
API_KEY: str = os.environ["API_KEY"]
