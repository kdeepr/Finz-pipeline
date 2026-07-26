"""
Self-verifying OAuth `state` parameter: no server-side storage at all.

The original implementation stored a random state token in Mongo when
`/connect` issued it, then looked it up again in `/callback`. That works
right up until anything disrupts continuity between those two requests -
an in-memory (mongomock/TESTING=true) database wiped by a process restart,
a `--reload` reload triggered by an unrelated file change mid-login, or
multiple worker processes each with their own store. All of those produced
the exact same symptom: "Unrecognized or expired OAuth state," even on a
completely valid, fresh connect attempt - the state was real, but whatever
stored it was gone by the time the callback ran.

A signed, timestamped token sidesteps the whole problem: `/callback` verifies
the state using only math (HMAC-SHA256) and the app's own already-configured
QBO_CLIENT_SECRET, not a lookup against anything that can be wiped or
inconsistent across processes. This is a standard OAuth pattern ("self-encoded
state") precisely because it removes the server-side storage dependency.
"""
import hashlib
import hmac
import secrets
import time

from app.config import Settings

MAX_AGE_SECONDS = 600  # 10 minutes - plenty for a login + consent click-through


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
