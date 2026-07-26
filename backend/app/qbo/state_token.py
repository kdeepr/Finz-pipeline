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
import logging
import secrets
import time

from app.config import Settings

logger = logging.getLogger("qbo.state_token")

MAX_AGE_SECONDS = 1800  # 30 minutes - a single-user local dev setup doesn't need OAuth's
# usual tight CSRF-window assumptions (there's no attacker racing to reuse this state
# against a shared, internet-facing server); this just needs to comfortably outlast
# however long a login + consent click-through actually takes in practice.


def _secret_fingerprint(settings: Settings) -> str:
    # Never logs the actual secret - just enough of a hash to tell whether
    # generate_state and verify_state saw the SAME secret value, which is
    # the one thing that can make an otherwise-correct HMAC fail to verify.
    return hashlib.sha256((settings.qbo_client_secret or "").encode()).hexdigest()[:12]


def generate_state(settings: Settings) -> str:
    nonce = secrets.token_urlsafe(16)
    timestamp = str(int(time.time()))
    signature = _sign(settings, nonce, timestamp)
    state = f"{nonce}.{timestamp}.{signature}"
    logger.warning(
        "QBO_STATE_DEBUG generate: state=%s secret_fp=%s secret_len=%d",
        state, _secret_fingerprint(settings), len(settings.qbo_client_secret or ""),
    )
    return state


def verify_state(settings: Settings, state: str) -> bool:
    logger.warning(
        "QBO_STATE_DEBUG verify: received=%r secret_fp=%s secret_len=%d",
        state, _secret_fingerprint(settings), len(settings.qbo_client_secret or ""),
    )
    parts = state.split(".")
    if len(parts) != 3:
        logger.warning("QBO_STATE_DEBUG verify: FAIL wrong part count=%d parts=%r", len(parts), parts)
        return False
    nonce, timestamp, signature = parts
    if not timestamp.isdigit():
        logger.warning("QBO_STATE_DEBUG verify: FAIL timestamp not numeric=%r", timestamp)
        return False
    expected = _sign(settings, nonce, timestamp)
    if not hmac.compare_digest(signature, expected):
        logger.warning("QBO_STATE_DEBUG verify: FAIL signature mismatch got=%s expected=%s", signature, expected)
        return False
    age = time.time() - int(timestamp)
    if age > MAX_AGE_SECONDS:
        logger.warning("QBO_STATE_DEBUG verify: FAIL expired age=%.1fs max=%d", age, MAX_AGE_SECONDS)
        return False
    logger.warning("QBO_STATE_DEBUG verify: OK age=%.1fs", age)
    return True


def _sign(settings: Settings, nonce: str, timestamp: str) -> str:
    key = (settings.qbo_client_secret or "").encode()
    message = f"{nonce}.{timestamp}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()
