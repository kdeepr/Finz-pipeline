import io
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sample_bank_exports"

ALL_SOURCE_FILES = [
    "operating_checking_2026_04.csv",
    "operating_checking_2026_05.csv",
    "operating_checking_2026_06.csv",
    "tax_reserve_2026_04.csv",
    "tax_reserve_2026_05.csv",
    "tax_reserve_2026_06.csv",
    "operating_checking_2026_04_15_to_2026_05_15.csv",
    "operating_checking_2026_05_15_to_2026_06_15.csv",
    "operating_checking_2026_06_10_to_2026_07_10.csv",
]


def _ingest_full_dataset(client):
    profile_id = client.get("/api/column-mappings").json()[0]["id"]
    for filename in ALL_SOURCE_FILES:
        content = (DATA_DIR / filename).read_bytes()
        files = {"file": (filename, io.BytesIO(content), "text/csv")}
        resp = client.post("/api/uploads", files=files, data={"mapping_profile_id": profile_id})
        assert resp.status_code == 200, resp.text


def _txn_by_query(client, q, status="ok"):
    # Several vendors (Shell, Staples, ...) recur every month with an identical
    # description, so more than one match is expected - they must all share the
    # same classification, which is exactly what these tests check.
    results = client.get("/api/transactions", params={"q": q, "status": status, "limit": 50}).json()
    assert len(results) >= 1, f"expected at least 1 match for '{q}', got 0"
    return results[0]


def test_full_dataset_classifies_with_zero_uncategorized(client):
    _ingest_full_dataset(client)
    result = client.post("/api/classification/run").json()
    assert result["classified"] == 195

    uncategorized = client.get(
        "/api/transactions", params={"status": "ok", "q": ""}
    ).json()
    # every "ok" transaction must have a real transaction_type, never left uncategorized
    all_ok = client.get("/api/transactions", params={"status": "ok", "limit": 300}).json()
    assert len(all_ok) == 195
    uncategorized_ones = [t for t in all_ok if t["transaction_type"] == "uncategorized"]
    assert uncategorized_ones == []


def test_equipment_install_is_revenue_not_fixed_asset(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    txn = _txn_by_query(client, "RIVERSIDE PEDIATRICS EQUIPMENT INSTALL")
    assert txn["transaction_type"] == "revenue"
    assert txn["qbo_account"] == "4010"


def test_tool_package_purchase_is_fixed_asset(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    txn = _txn_by_query(client, "MILWAUKEE COMMERCIAL TOOL PACKAGE")
    assert txn["transaction_type"] == "fixed_asset"
    assert txn["qbo_account"] == "1500"


def test_refund_reduces_revenue_account(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    txn = _txn_by_query(client, "ACH REFUND TO HARBORVIEW APARTMENTS")
    assert txn["transaction_type"] == "refund"
    assert txn["qbo_account"] == "4100"


def test_transfers_have_no_pnl_account(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    legs = client.get("/api/transactions", params={"q": "TAX RESERVE TRANSFER", "limit": 50}).json()
    assert len(legs) == 12  # 6 checking legs + 6 reserve legs, all "ok"
    assert all(t["transaction_type"] == "transfer" for t in legs)
    assert all(t["qbo_account"] is None for t in legs)


def test_owner_activity_both_directions(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    contribution = _txn_by_query(client, "OWNER CAPITAL")
    distribution = _txn_by_query(client, "OWNER DISTRIBUTION")
    assert contribution["transaction_type"] == "owner_activity"
    assert distribution["transaction_type"] == "owner_activity"
    assert contribution["qbo_account"] == distribution["qbo_account"] == "3000"
    assert contribution["counterparty"] == distribution["counterparty"] == "MAYA PATEL"


def test_vehicle_repair_is_not_confused_with_fuel(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    fuel = _txn_by_query(client, "SHELL OIL")
    repair = client.get("/api/transactions", params={"q": "FLEET AUTO CARE", "limit": 10}).json()[0]
    assert fuel["qbo_account"] == "6020"
    assert repair["qbo_account"] == "6100"


def test_same_vendor_different_name_variants_classify_consistently(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    variant_a = _txn_by_query(client, "ACH APEX ELECTRICAL")
    variant_b = _txn_by_query(client, "APEX ELEC LLC")
    assert variant_a["qbo_account"] == variant_b["qbo_account"] == "5010"
    assert variant_a["transaction_type"] == variant_b["transaction_type"] == "cogs"


def test_review_correction_is_applied_and_learned_for_future_uploads(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")

    txn = _txn_by_query(client, "STAPLES 001422")
    assert txn["qbo_account"] == "6090"

    # Reviewer corrects it (e.g. to Office & General was actually fine, but let's
    # simulate a genuine correction: staples purchase should have been "6100").
    resp = client.post(
        f"/api/transactions/{txn['id']}/review",
        json={"transaction_type": "operating_expense", "qbo_account": "6100", "counterparty": "Staples", "apply_to_similar": True},
    )
    assert resp.status_code == 200
    corrected = resp.json()
    assert corrected["classification_status"] == "corrected"
    assert corrected["classification_source"] == "user"

    rules = client.get("/api/classification/rules").json()
    assert any(r["qbo_account"] == "6100" and "STAPLES" in r["signature"] for r in rules)

    # A brand-new upload with the same recurring Staples charge (different card
    # ref number) should now be auto-classified via the learned correction,
    # without needing the reviewer to fix it again.
    new_csv = (
        "Bank Transaction ID,Transaction Date,Posted Date,Description,Amount (USD),Currency,Bank Account\n"
        "BF-NEW-0001,2026-07-01,2026-07-01,STAPLES 001422 OFFICE SUPPLIES,-45.00,USD,Operating Checking\n"
    )
    profile_id = client.get("/api/column-mappings").json()[0]["id"]
    files = {"file": ("new_export.csv", io.BytesIO(new_csv.encode()), "text/csv")}
    upload_resp = client.post("/api/uploads", files=files, data={"mapping_profile_id": profile_id})
    assert upload_resp.status_code == 200

    client.post("/api/classification/run")
    new_txn = client.get("/api/transactions", params={"q": "STAPLES 001422", "status": "ok"}).json()
    latest = next(t for t in new_txn if t["external_id"] == "BF-NEW-0001")
    assert latest["qbo_account"] == "6100"
    assert latest["classification_source"] == "learned_rule"


def test_reviewed_transaction_is_not_overwritten_by_reclassify(client):
    _ingest_full_dataset(client)
    client.post("/api/classification/run")
    txn = _txn_by_query(client, "SHELL OIL")
    client.post(
        f"/api/transactions/{txn['id']}/review",
        json={"transaction_type": "operating_expense", "qbo_account": "6020", "counterparty": "Shell", "apply_to_similar": False},
    )
    # re-running classification globally must not touch a reviewed transaction
    client.post("/api/classification/run")
    refreshed = client.get(f"/api/transactions/{txn['id']}").json()
    assert refreshed["normalized"]["classification_status"] == "reviewed"
