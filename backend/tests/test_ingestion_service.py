"""
End-to-end ingestion tests driven through the real HTTP API, using the actual
sample bank exports checked into data/sample_bank_exports/ (derived directly
from the challenge dataset, values unaltered). This exercises the full 4.2
flow: upload -> column mapping -> raw preservation -> normalization ->
cross-file duplicate detection -> flagging.
"""
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
    # These three overlap date ranges with files already uploaded above and
    # re-send some of the same bank transactions - exactly the scenario PDF
    # 4.2 calls out ("duplicates created by overlapping source files").
    "operating_checking_2026_04_15_to_2026_05_15.csv",
    "operating_checking_2026_05_15_to_2026_06_15.csv",
    "operating_checking_2026_06_10_to_2026_07_10.csv",
]

KNOWN_OVERLAP_DUPLICATE_IDS = {
    "BF-202604-0001",
    "BF-202605-0071",
    "BF-202605-0096",
    "BF-202606-0136",
    "BF-202606-0171",
}


def _default_profile_id(client) -> str:
    profiles = client.get("/api/column-mappings").json()
    assert len(profiles) == 1
    return profiles[0]["id"]


def _upload(client, filename: str, profile_id: str):
    content = (DATA_DIR / filename).read_bytes()
    files = {"file": (filename, io.BytesIO(content), "text/csv")}
    data = {"mapping_profile_id": profile_id}
    resp = client.post("/api/uploads", files=files, data=data)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_default_mapping_profile_is_seeded_on_startup(client):
    profiles = client.get("/api/column-mappings").json()
    assert profiles[0]["name"] == "brightfix_bank_csv_v1"


def test_full_dataset_ingest_counts_and_cross_file_duplicates(client):
    profile_id = _default_profile_id(client)

    total_ok = total_dup = total_review = total_rows = 0
    for filename in ALL_SOURCE_FILES:
        batch = _upload(client, filename, profile_id)
        total_rows += batch["row_count"]
        total_ok += batch["ok_count"]
        total_dup += batch["duplicate_count"]
        total_review += batch["needs_review_count"]

    assert total_rows == 200
    assert total_dup == 5
    assert total_review == 0
    assert total_ok == 195

    duplicates = client.get("/api/transactions", params={"status": "duplicate"}).json()
    dup_external_ids = {t["external_id"] for t in duplicates}
    assert dup_external_ids == KNOWN_OVERLAP_DUPLICATE_IDS

    for txn in duplicates:
        assert txn["duplicate_of"] is not None
        original = client.get(f"/api/transactions/{txn['duplicate_of']}").json()
        assert original["normalized"]["external_id"] == txn["external_id"]
        assert original["normalized"]["status"] == "ok"


def test_raw_record_preserved_unaltered(client):
    profile_id = _default_profile_id(client)
    _upload(client, "operating_checking_2026_04.csv", profile_id)

    txns = client.get(
        "/api/transactions", params={"q": "PARKSIDE COMMERCIAL MGMT"}
    ).json()
    assert len(txns) == 1
    detail = client.get(f"/api/transactions/{txns[0]['id']}").json()

    assert detail["normalized"]["amount"] == -8200.0
    assert detail["normalized"]["direction"] == "debit"
    assert detail["normalized"]["bank_account"] == "Operating Checking"
    # Raw record keeps the original column names/values verbatim - including
    # the exact "Amount (USD)" string, not the normalizer's parsed float.
    assert detail["raw"]["fields"]["Amount (USD)"] == "-8200.0"
    assert detail["raw"]["fields"]["Description"] == "ACH PARKSIDE COMMERCIAL MGMT RENT APR"


def test_transfer_legs_both_ingest_cleanly(client):
    profile_id = _default_profile_id(client)
    _upload(client, "operating_checking_2026_04.csv", profile_id)
    _upload(client, "tax_reserve_2026_04.csv", profile_id)

    checking_leg = client.get("/api/transactions", params={"q": "TRANSFER TO TAX RESERVE"}).json()
    reserve_leg = client.get("/api/transactions", params={"q": "TRANSFER FROM OPERATING"}).json()
    assert len(checking_leg) == 2
    assert len(reserve_leg) == 2
    assert all(t["bank_account"] == "Operating Checking" for t in checking_leg)
    assert all(t["bank_account"] == "Tax Reserve" for t in reserve_leg)
    assert all(t["status"] == "ok" for t in checking_leg + reserve_leg)


def test_flags_unsafe_rows_instead_of_dropping(client):
    profile_id = _default_profile_id(client)
    bad_csv = (
        "Bank Transaction ID,Transaction Date,Posted Date,Description,Amount (USD),Currency,Bank Account\n"
        "BF-BAD-0001,not-a-date,2026-04-01,,N/A,USD,Mystery Account\n"
    )
    files = {"file": ("bad_export.csv", io.BytesIO(bad_csv.encode()), "text/csv")}
    resp = client.post("/api/uploads", files=files, data={"mapping_profile_id": profile_id})
    assert resp.status_code == 200
    batch = resp.json()
    assert batch["row_count"] == 1
    assert batch["needs_review_count"] == 1
    assert batch["ok_count"] == 0
    assert batch["duplicate_count"] == 0

    flagged = client.get("/api/transactions", params={"status": "needs_review"}).json()
    assert len(flagged) == 1
    reasons = set(flagged[0]["flags"])
    assert "unparseable_transaction_date" in reasons
    assert "missing_description" in reasons
    assert "unparseable_amount" in reasons
    assert "unrecognized_bank_account" in reasons


def test_mapping_mismatch_returns_400(client):
    profile_id = _default_profile_id(client)
    wrong_csv = "Date,Amount\n2026-04-01,100\n"
    files = {"file": ("wrong_columns.csv", io.BytesIO(wrong_csv.encode()), "text/csv")}
    resp = client.post("/api/uploads", files=files, data={"mapping_profile_id": profile_id})
    assert resp.status_code == 400
    assert "references columns not present" in resp.json()["detail"]
