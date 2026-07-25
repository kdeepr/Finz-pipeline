def test_reconciliation_without_connection_returns_clear_400(client):
    resp = client.get("/api/reconciliation/2026-04")
    assert resp.status_code == 400
    assert "Not connected" in resp.json()["detail"]
