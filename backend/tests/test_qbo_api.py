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
