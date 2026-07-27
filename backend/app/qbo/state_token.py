import hashlib
import hmac
import secrets
import time

from app.config import Settings

MAX_AGE_SECONDS = 1800  # 30 minutes - a single-user local dev setup doesn't need OAuth's
# usual tight CSRF-window assumptions (there's no attacker racing to reuse this state
# against a shared, internet-facing server); this just needs to comfortably outlast
# however long a login + consent click-through actually takes in practice.


def generate_state(settings: Settings) -> str:
    nonce = secrets.token_urlsafe(16)
    timestamp = str(int(time.time()))
    signature = _sign(settings, nonce, timestamp)
    return f"{nonce}.{timestamp}.{signature}"


def verify_state(settings: Settings, state: str) -> bool:
    parts = state.split(".")
    if len(parts) != 3:
        return False
    nonce, timestamp, signature = parts
    if not timestamp.isdigit():
        return False
    expected = _sign(settings, nonce, timestamp)
    if not hmac.compare_digest(signature, expected):
        return False
    return (time.time() - int(timestamp)) <= MAX_AGE_SECONDS


def _sign(settings: Settings, nonce: str, timestamp: str) -> str:
    key = (settings.qbo_client_secret or "").encode()
    message = f"{nonce}.{timestamp}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()
