def test_status_reports_not_connected_by_default(client):
    resp = client.get("/api/qbo/status")
    assert resp.status_code == 200
    assert resp.json() == {"connected": False}


def test_connect_without_credentials_returns_clear_400(client):
    resp = client.get("/api/qbo/connect")
    assert resp.status_code == 400
    assert "QBO_CLIENT_ID" in resp.json()["detail"]


def test_sync_without_connection_returns_clear_400(client):
    resp = client.post("/api/qbo/sync")
    assert resp.status_code == 400
    assert "Not connected" in resp.json()["detail"]


def test_accounts_sync_without_connection_returns_clear_400(client):
    resp = client.post("/api/qbo/accounts/sync")
    assert resp.status_code == 400
    assert "Not connected" in resp.json()["detail"]


def _seed_state(client, state="test-state"):
    from app.db import get_db

    get_db()["qbo_oauth_state"].insert_one({"state": state})
    return state


def test_callback_with_unknown_state_redirects_to_frontend_with_error(client):
    resp = client.get(
        "/api/qbo/callback",
        params={"code": "abc", "state": "never-issued", "realmId": "123"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("http://localhost:5173/?")
    assert "qbo_status=error" in location
    assert "expired" in location.lower() or "unrecognized" in location.lower()


def test_callback_success_redirects_to_frontend_connected_and_saves_tokens(client, monkeypatch):
    from app.db import get_db
    from app.qbo import connection_store

    state = _seed_state(client)
    monkeypatch.setattr(
        "app.api.qbo.oauth.exchange_code_for_tokens",
        lambda settings, code: {"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
    )

    resp = client.get(
        "/api/qbo/callback",
        params={"code": "abc", "state": state, "realmId": "realm-123"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("http://localhost:5173/?")
    assert "qbo_status=connected" in location
    assert "realm_id=realm-123" in location

    db = get_db()
    connection = connection_store.get_connection(db)
    assert connection["realm_id"] == "realm-123"
    assert connection["access_token"] == "at"
    # state is single-use
    assert db["qbo_oauth_state"].find_one({"state": state}) is None


def test_callback_token_exchange_failure_redirects_with_error_instead_of_crashing(client, monkeypatch):
    from app.qbo.oauth import QBOOAuthError

    state = _seed_state(client)

    def boom(settings, code):
        raise QBOOAuthError("Token exchange failed (401): invalid_client")

    monkeypatch.setattr("app.api.qbo.oauth.exchange_code_for_tokens", boom)

    resp = client.get(
        "/api/qbo/callback",
        params={"code": "abc", "state": state, "realmId": "realm-123"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "qbo_status=error" in location
    assert "invalid_client" in location
