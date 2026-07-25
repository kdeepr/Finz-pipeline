"""
Sync-orchestration tests using a FakeQBOClient in place of a real QBO
connection - there's no live sandbox to call from this environment, so what's
verified here is the logic that decides *what* to sync, *when* to skip
already-synced work, and *how* transfer pairs get linked - all of which is
independent of the actual HTTP transport.
"""
from app.classification.coa import load_chart_of_accounts
from app.db import get_db
from app.models.common import new_id
from app.qbo.account_ids import build_mapping_from_qbo_accounts
from app.qbo.mapper import BANK_ACCOUNT_NO
from app.qbo.sync_service import sync_pending


class FakeQBOClient:
    def __init__(self):
        self.created: list[tuple[str, dict]] = []
        self._next_id = 1000
        self.fail_next = False

    def create_entity(self, entity_type: str, body: dict) -> dict:
        if self.fail_next:
            from app.qbo.client import QBOAPIError

            self.fail_next = False
            raise QBOAPIError(500, "simulated transient failure")
        self._next_id += 1
        self.created.append((entity_type, body))
        return {"Id": str(self._next_id)}


def _seed_account_mapping(db):
    qbo_accounts = [
        {"Id": f"qbo-{a['Account No.']}", "Name": a["Account Name"], "AcctNum": a["Account No."]}
        for a in load_chart_of_accounts()
    ]
    build_mapping_from_qbo_accounts(db, qbo_accounts, load_chart_of_accounts())


def _insert_txn(db, **fields):
    doc = {
        "id": new_id(),
        "batch_id": "b1",
        "raw_id": "r1",
        "external_id": None,
        "posted_date": None,
        "currency": "USD",
        "bank_account_raw": fields.get("bank_account"),
        "description_raw": fields.get("description_normalized"),
        "dedup_key": new_id(),
        "duplicate_of": None,
        "flags": [],
        "counterparty": None,
        "qbo_account_name": None,
        "classification_source": "rule",
        "qbo_txn_id": None,
        "qbo_sync_status": None,
        "qbo_sync_error": None,
        "qbo_synced_at": None,
        "created_at": "2026-04-01T00:00:00+00:00",
        "updated_at": "2026-04-01T00:00:00+00:00",
        "status": "ok",
        "classification_status": "auto",
        "classification_confidence": 1.0,
        "qbo_account": None,
    }
    doc.update(fields)
    db["normalized_transactions"].insert_one(doc)
    return doc


def test_high_confidence_auto_classified_transaction_syncs(client):
    db = get_db()
    _seed_account_mapping(db)
    _insert_txn(
        db,
        transaction_type="operating_expense",
        qbo_account="6010",
        bank_account="Operating Checking",
        direction="debit",
        amount=-8200.0,
        transaction_date="2026-04-01",
        description_normalized="RENT",
    )
    fake = FakeQBOClient()
    result = sync_pending(db, client=fake)
    assert result["synced"] == 1
    assert fake.created[0][0] == "purchase"

    txn = db["normalized_transactions"].find_one({})
    assert txn["qbo_sync_status"] == "synced"
    assert txn["qbo_txn_id"] is not None


def test_low_confidence_gemini_classification_is_not_synced_until_reviewed(client):
    db = get_db()
    _seed_account_mapping(db)
    _insert_txn(
        db,
        transaction_type="operating_expense",
        qbo_account="6090",
        bank_account="Operating Checking",
        direction="debit",
        amount=-45.0,
        transaction_date="2026-04-01",
        description_normalized="UNKNOWN MERCHANT",
        classification_source="gemini",
        classification_confidence=0.6,
    )
    fake = FakeQBOClient()
    result = sync_pending(db, client=fake)
    assert result["synced"] == 0
    assert fake.created == []


def test_reviewed_transaction_syncs_regardless_of_confidence(client):
    db = get_db()
    _seed_account_mapping(db)
    _insert_txn(
        db,
        transaction_type="operating_expense",
        qbo_account="6090",
        bank_account="Operating Checking",
        direction="debit",
        amount=-45.0,
        transaction_date="2026-04-01",
        description_normalized="UNKNOWN MERCHANT",
        classification_source="user",
        classification_status="reviewed",
        classification_confidence=1.0,
    )
    fake = FakeQBOClient()
    result = sync_pending(db, client=fake)
    assert result["synced"] == 1


def test_rerunning_sync_does_not_duplicate_post(client):
    db = get_db()
    _seed_account_mapping(db)
    _insert_txn(
        db,
        transaction_type="operating_expense",
        qbo_account="6010",
        bank_account="Operating Checking",
        direction="debit",
        amount=-8200.0,
        transaction_date="2026-04-01",
        description_normalized="RENT",
    )
    fake = FakeQBOClient()
    sync_pending(db, client=fake)
    sync_pending(db, client=fake)  # run again
    assert len(fake.created) == 1  # only ever posted once


def test_failed_sync_can_be_retried(client):
    db = get_db()
    _seed_account_mapping(db)
    _insert_txn(
        db,
        transaction_type="operating_expense",
        qbo_account="6010",
        bank_account="Operating Checking",
        direction="debit",
        amount=-8200.0,
        transaction_date="2026-04-01",
        description_normalized="RENT",
    )
    fake = FakeQBOClient()
    fake.fail_next = True
    result = sync_pending(db, client=fake)
    assert result["failed"] == 1
    assert result["synced"] == 0
    txn = db["normalized_transactions"].find_one({})
    assert txn["qbo_sync_status"] == "failed"
    assert "simulated transient failure" in txn["qbo_sync_error"]

    # retry: same call, but the client no longer fails
    result2 = sync_pending(db, client=fake)
    assert result2["synced"] == 1
    txn = db["normalized_transactions"].find_one({})
    assert txn["qbo_sync_status"] == "synced"


def test_transfer_pair_only_makes_one_api_call(client):
    db = get_db()
    _seed_account_mapping(db)
    debit_leg = _insert_txn(
        db,
        transaction_type="transfer",
        qbo_account=None,
        bank_account="Operating Checking",
        counterparty="Tax Reserve",
        direction="debit",
        amount=-5000.0,
        transaction_date="2026-04-10",
        description_normalized="ONLINE TRANSFER TO TAX RESERVE",
    )
    credit_leg = _insert_txn(
        db,
        transaction_type="transfer",
        qbo_account=None,
        bank_account="Tax Reserve",
        counterparty="Operating Checking",
        direction="credit",
        amount=5000.0,
        transaction_date="2026-04-10",
        description_normalized="ONLINE TRANSFER FROM OPERATING",
    )
    fake = FakeQBOClient()
    result = sync_pending(db, client=fake)
    assert result["synced"] == 1
    assert result["linked"] == 1
    assert len([c for c in fake.created if c[0] == "transfer"]) == 1

    debit_after = db["normalized_transactions"].find_one({"id": debit_leg["id"]})
    credit_after = db["normalized_transactions"].find_one({"id": credit_leg["id"]})
    assert debit_after["qbo_sync_status"] == "synced"
    assert credit_after["qbo_sync_status"] == "linked"
    assert credit_after["qbo_txn_id"] == debit_after["qbo_txn_id"]


def test_transfer_pairing_is_order_independent(client):
    """Same scenario as above, but the credit leg is inserted first - pairing
    must not depend on which leg happens to be processed first."""
    db = get_db()
    _seed_account_mapping(db)
    credit_leg = _insert_txn(
        db,
        transaction_type="transfer",
        qbo_account=None,
        bank_account="Tax Reserve",
        counterparty="Operating Checking",
        direction="credit",
        amount=7000.0,
        transaction_date="2026-05-10",
        description_normalized="ONLINE TRANSFER FROM OPERATING",
    )
    debit_leg = _insert_txn(
        db,
        transaction_type="transfer",
        qbo_account=None,
        bank_account="Operating Checking",
        counterparty="Tax Reserve",
        direction="debit",
        amount=-7000.0,
        transaction_date="2026-05-10",
        description_normalized="ONLINE TRANSFER TO TAX RESERVE",
    )
    fake = FakeQBOClient()
    sync_pending(db, client=fake)
    debit_after = db["normalized_transactions"].find_one({"id": debit_leg["id"]})
    credit_after = db["normalized_transactions"].find_one({"id": credit_leg["id"]})
    assert debit_after["qbo_sync_status"] == "synced"
    assert credit_after["qbo_sync_status"] == "linked"
    assert credit_after["qbo_txn_id"] == debit_after["qbo_txn_id"]
