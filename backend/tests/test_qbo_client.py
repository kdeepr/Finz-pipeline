"""
QBOClient tests using a fake `transport` in place of `requests` - there's no
live sandbox to call from this environment (see connect_flow.md), so what's
verified here is everything up to the actual network call: URL construction,
header/payload passthrough, response parsing, and - the point of this file -
that a token-refresh failure surfaces as the one exception type
(QBOAPIError) every calling code path already knows how to handle, rather
than a second, easily-forgotten exception type.
"""
import pytest

from app.config import Settings
from app.db import get_db
from app.qbo import connection_store
from app.qbo.client import QBOAPIError, QBOClient, QBONotConnectedError
from app.qbo.oauth import QBOOAuthError


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json_data


class FakeTransport:
    def __init__(self, post_response=None, get_response=None):
        self.post_response = post_response
        self.get_response = get_response
        self.calls = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json, headers))
        return self.post_response

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append(("GET", url, params, headers))
        return self.get_response


def _settings():
    return Settings(qbo_client_id="id", qbo_client_secret="secret", qbo_environment="sandbox", testing=True)


def test_create_entity_without_connection_raises_not_connected(client):
    db = get_db()
    qbo_client = QBOClient(db, _settings(), transport=FakeTransport())
    with pytest.raises(QBONotConnectedError):
        qbo_client.create_entity("purchase", {})


def test_create_entity_uses_sandbox_base_url_and_returns_capitalized_entity(client):
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    transport = FakeTransport(post_response=FakeResponse(200, {"Purchase": {"Id": "42"}}))
    qbo_client = QBOClient(db, _settings(), transport=transport)

    result = qbo_client.create_entity("purchase", {"Amount": 10})

    assert result == {"Id": "42"}
    method, url, body, headers = transport.calls[0]
    assert url == "https://sandbox-quickbooks.api.intuit.com/v3/company/realm-1/purchase"
    assert body == {"Amount": 10}
    assert headers["Authorization"] == "Bearer at"


def test_create_entity_raises_qbo_api_error_on_failure_status(client):
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    transport = FakeTransport(post_response=FakeResponse(400, text="Bad Request: invalid AccountRef"))
    qbo_client = QBOClient(db, _settings(), transport=transport)

    with pytest.raises(QBOAPIError) as exc_info:
        qbo_client.create_entity("purchase", {})
    assert "invalid AccountRef" in str(exc_info.value)


def test_expired_token_triggers_refresh_and_persists_new_tokens(client, monkeypatch):
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "old-access", "old-refresh", expires_in=-10)  # already expired

    monkeypatch.setattr(
        "app.qbo.client.oauth.refresh_tokens",
        lambda settings, refresh_token: {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600},
    )
    transport = FakeTransport(post_response=FakeResponse(200, {"Purchase": {"Id": "1"}}))
    qbo_client = QBOClient(db, _settings(), transport=transport)

    qbo_client.create_entity("purchase", {})

    _, _, _, headers = transport.calls[0]
    assert headers["Authorization"] == "Bearer new-access"
    connection = connection_store.get_connection(db)
    assert connection["access_token"] == "new-access"


def test_token_refresh_failure_surfaces_as_qbo_api_error_not_oauth_error(client, monkeypatch):
    """
    This is the point of this test: refresh_tokens raises QBOOAuthError, but
    every caller (run_sync's per-transaction loop, the accounts/sync and
    reconciliation endpoints) only catches QBOAPIError alongside
    QBONotConnectedError. If this leaked through as QBOOAuthError it would
    crash those call sites with an unhandled exception instead of a clean
    error.
    """
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "old-access", "old-refresh", expires_in=-10)

    def boom(settings, refresh_token):
        raise QBOOAuthError("Token refresh failed (400): invalid_grant")

    monkeypatch.setattr("app.qbo.client.oauth.refresh_tokens", boom)
    qbo_client = QBOClient(db, _settings(), transport=FakeTransport())

    with pytest.raises(QBOAPIError) as exc_info:
        qbo_client.create_entity("purchase", {})
    assert "invalid_grant" in str(exc_info.value)


def test_query_hits_query_endpoint_with_sql_param(client):
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    transport = FakeTransport(get_response=FakeResponse(200, {"QueryResponse": {"Account": []}}))
    qbo_client = QBOClient(db, _settings(), transport=transport)

    result = qbo_client.query("SELECT * FROM Account")

    assert result == {"QueryResponse": {"Account": []}}
    method, url, params, _ = transport.calls[0]
    assert url == "https://sandbox-quickbooks.api.intuit.com/v3/company/realm-1/query"
    assert params == {"query": "SELECT * FROM Account"}


def test_get_profit_and_loss_hits_reports_endpoint_with_cash_basis(client):
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    transport = FakeTransport(get_response=FakeResponse(200, {"Rows": {"Row": []}}))
    qbo_client = QBOClient(db, _settings(), transport=transport)

    qbo_client.get_profit_and_loss("2026-04-01", "2026-04-30")

    method, url, params, _ = transport.calls[0]
    assert url == "https://sandbox-quickbooks.api.intuit.com/v3/company/realm-1/reports/ProfitAndLoss"
    assert params == {"start_date": "2026-04-01", "end_date": "2026-04-30", "accounting_method": "Cash"}


def test_production_environment_uses_production_base_url(client):
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    settings = Settings(qbo_client_id="id", qbo_client_secret="secret", qbo_environment="production", testing=True)
    transport = FakeTransport(get_response=FakeResponse(200, {}))
    qbo_client = QBOClient(db, settings, transport=transport)

    qbo_client.query("SELECT * FROM Account")

    _, url, _, _ = transport.calls[0]
    assert url.startswith("https://quickbooks.api.intuit.com/")
