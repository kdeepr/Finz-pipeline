"""
Tests app/qbo/oauth.py's HTTP logic directly (monkeypatching requests.post,
since there's no live Intuit endpoint to call from this environment) -
status-code handling and, specifically, that a network-level failure
(timeout, DNS, connection refused) surfaces as QBOOAuthError rather than an
unhandled requests exception escaping through /api/qbo/callback.
"""
import pytest
import requests

from app.config import Settings
from app.qbo.oauth import QBOOAuthError, build_authorization_url, exchange_code_for_tokens, refresh_tokens


def _settings():
    return Settings(
        qbo_client_id="my-client-id",
        qbo_client_secret="my-secret",
        qbo_redirect_uri="http://localhost:8000/api/qbo/callback",
        testing=True,
    )


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text

    def json(self):
        return self._json_data


def test_build_authorization_url_includes_required_params():
    url = build_authorization_url(_settings(), state="abc123")
    assert url.startswith("https://appcenter.intuit.com/connect/oauth2?")
    assert "client_id=my-client-id" in url
    assert "state=abc123" in url
    assert "scope=com.intuit.quickbooks.accounting" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fqbo%2Fcallback" in url


def test_exchange_code_for_tokens_returns_parsed_json_on_success(monkeypatch):
    monkeypatch.setattr(
        "app.qbo.oauth.requests.post",
        lambda *a, **k: FakeResponse(200, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}),
    )
    tokens = exchange_code_for_tokens(_settings(), "auth-code")
    assert tokens["access_token"] == "at"


def test_exchange_code_for_tokens_raises_on_non_200(monkeypatch):
    monkeypatch.setattr("app.qbo.oauth.requests.post", lambda *a, **k: FakeResponse(400, text="invalid_grant"))
    with pytest.raises(QBOOAuthError) as exc_info:
        exchange_code_for_tokens(_settings(), "auth-code")
    assert "invalid_grant" in str(exc_info.value)


def test_exchange_code_for_tokens_network_failure_raises_qbo_oauth_error(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.ConnectionError("Name or service not known")

    monkeypatch.setattr("app.qbo.oauth.requests.post", boom)
    with pytest.raises(QBOOAuthError) as exc_info:
        exchange_code_for_tokens(_settings(), "auth-code")
    assert "Could not reach Intuit" in str(exc_info.value)


def test_refresh_tokens_network_failure_raises_qbo_oauth_error(monkeypatch):
    def boom(*a, **k):
        raise requests.exceptions.Timeout("Read timed out")

    monkeypatch.setattr("app.qbo.oauth.requests.post", boom)
    with pytest.raises(QBOOAuthError) as exc_info:
        refresh_tokens(_settings(), "refresh-token")
    assert "Could not reach Intuit" in str(exc_info.value)


def test_refresh_tokens_raises_on_non_200(monkeypatch):
    monkeypatch.setattr("app.qbo.oauth.requests.post", lambda *a, **k: FakeResponse(400, text="invalid_grant"))
    with pytest.raises(QBOOAuthError):
        refresh_tokens(_settings(), "refresh-token")
