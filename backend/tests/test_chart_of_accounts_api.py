def test_chart_of_accounts_returns_all_accounts(client):
    resp = client.get("/api/chart-of-accounts")
    assert resp.status_code == 200
    accounts = resp.json()
    codes = {a["Account No."] for a in accounts}
    assert "4000" in codes
    assert "6100" in codes
    assert len(accounts) == 21
