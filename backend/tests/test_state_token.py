import time

from app.config import Settings
from app.qbo import state_token


def _settings(secret="test-secret"):
    return Settings(qbo_client_secret=secret, testing=True)


def test_generated_state_verifies():
    settings = _settings()
    state = state_token.generate_state(settings)
    assert state_token.verify_state(settings, state)


def test_state_is_specific_to_the_signing_secret():
    state = state_token.generate_state(_settings("secret-a"))
    assert not state_token.verify_state(_settings("secret-b"), state)


def test_garbage_state_fails():
    assert not state_token.verify_state(_settings(), "garbage")
    assert not state_token.verify_state(_settings(), "a.b")
    assert not state_token.verify_state(_settings(), "")


def test_non_numeric_timestamp_fails():
    assert not state_token.verify_state(_settings(), "nonce.not-a-number.deadbeef")


def test_tampered_signature_fails():
    settings = _settings()
    state = state_token.generate_state(settings)
    nonce, ts, sig = state.split(".")
    flipped_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert not state_token.verify_state(settings, f"{nonce}.{ts}.{flipped_sig}")


def test_expired_state_fails():
    settings = _settings()
    nonce = "fixed-nonce"
    old_timestamp = str(int(time.time()) - state_token.MAX_AGE_SECONDS - 60)
    signature = state_token._sign(settings, nonce, old_timestamp)
    expired_state = f"{nonce}.{old_timestamp}.{signature}"
    assert not state_token.verify_state(settings, expired_state)


def test_each_generated_state_is_unique():
    settings = _settings()
    states = {state_token.generate_state(settings) for _ in range(20)}
    assert len(states) == 20
