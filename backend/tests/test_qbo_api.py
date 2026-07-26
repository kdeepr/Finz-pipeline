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


def _make_state():
    """A validly-signed state, generated exactly the way /connect would."""
    from app.config import get_settings
    from app.qbo import state_token

    return state_token.generate_state(get_settings())


def test_callback_with_garbled_state_redirects_to_frontend_with_error(client):
    resp = client.get(
        "/api/qbo/callback",
        params={"code": "abc", "state": "not-a-real-token", "realmId": "123"},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert location.startswith("http://localhost:5173/?")
    assert "qbo_status=error" in location
    assert "expired" in location.lower() or "unrecognized" in location.lower()


def test_callback_rejects_tampered_state_signature(client):
    state = _make_state()
    nonce, ts, _sig = state.split(".")
    tampered = f"{nonce}.{ts}.0000000000000000000000000000000000000000000000000000000000000000"

    resp = client.get(
        "/api/qbo/callback",
        params={"code": "abc", "state": tampered, "realmId": "123"},
        follow_redirects=False,
    )
    location = resp.headers["location"]
    assert "qbo_status=error" in location


def test_callback_state_survives_an_in_memory_db_reset(client):
    """
    This is the exact bug that was reported: a database-backed state lookup
    failed with "unrecognized or expired" on completely valid, fresh connect
    attempts whenever the backend process/in-memory store was disturbed
    between /connect and /callback. A signed state has no such dependency -
    resetting the database entirely between generating and verifying it must
    not affect the outcome.
    """
    from app.db import reset_client_cache

    state = _make_state()
    reset_client_cache()  # simulates exactly what a backend restart did before

    resp = client.get(
        "/api/qbo/callback",
        params={"state": state, "error": "access_denied", "error_description": "just checking state verification"},
        follow_redirects=False,
    )
    location = resp.headers["location"]
    # Reaches the error/code branch (state verification passed) rather than
    # the "unrecognized or expired state" branch.
    assert "just+checking" in location or "just%20checking" in location


def test_callback_success_redirects_to_frontend_connected_and_saves_tokens(client, monkeypatch):
    from app.db import get_db
    from app.qbo import connection_store

    state = _make_state()
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


def test_callback_token_exchange_failure_redirects_with_error_instead_of_crashing(client, monkeypatch):
    from app.qbo.oauth import QBOOAuthError

    state = _make_state()

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


def test_callback_surfaces_intuit_side_error_instead_of_generic_422(client):
    # Intuit redirects here with `error`/`error_description` and no `code`/
    # `realmId` when something fails on its side (denied consent, a
    # misconfigured app) - state IS still echoed back. Before this was
    # handled, FastAPI's default validation turned this into an opaque
    # "field required" 422 that hid Intuit's actual reason.
    state = _make_state()
    resp = client.get(
        "/api/qbo/callback",
        params={"state": state, "error": "access_denied", "error_description": "The user denied access to your application."},
        follow_redirects=False,
    )
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "qbo_status=error" in location
    assert "denied+access" in location or "denied%20access" in location


def test_callback_missing_code_without_explicit_error_still_redirects_cleanly(client):
    state = _make_state()
    resp = client.get("/api/qbo/callback", params={"state": state}, follow_redirects=False)
    assert resp.status_code in (302, 307)
    location = resp.headers["location"]
    assert "qbo_status=error" in location
    assert "did+not+return" in location or "did%20not%20return" in location
