def test_reconciliation_without_connection_returns_clear_400(client):
    resp = client.get("/api/reconciliation/2026-04")
    assert resp.status_code == 400
    assert "Not connected" in resp.json()["detail"]


def test_reconciliation_surfaces_qbo_api_failure_instead_of_crashing(client, monkeypatch):
    from app.db import get_db
    from app.qbo import connection_store
    from app.qbo.client import QBOAPIError

    connection_store.save_tokens(get_db(), "realm-1", "at", "rt", 3600)

    def boom(db, period, settings=None, client=None):
        raise QBOAPIError(400, "Invalid report date range")

    monkeypatch.setattr("app.api.reconciliation.reconcile", boom)

    resp = client.get("/api/reconciliation/2026-04")
    assert resp.status_code == 502
    assert "Invalid report date range" in resp.json()["detail"]
