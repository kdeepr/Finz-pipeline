"""
Sync orchestration (PDF 4.5). Idempotency and safe retries both come from one
idea: a transaction's own qbo_sync_status is the source of truth for whether
it needs an API call, so the sync query itself excludes anything already
"synced" or "linked" - running sync twice in a row simply finds nothing left
to do the second time, rather than needing a separate "already posted?"
check per transaction.

Transfers are processed in two passes so pairing is order-independent: all
outgoing (debit) legs sync first as a single QBO Transfer call each, then
their paired incoming (credit) legs are marked "linked" to that same Transfer
Id (no second API call - one Transfer object already moved both accounts).
Any credit leg whose debit pair isn't in *this* batch (e.g. it synced in an
earlier run) is linked by looking up the existing sync record directly.
"""
from datetime import datetime, timezone

from pymongo.database import Database

from app.classification.coa import account_name
from app.config import Settings, get_settings
from app.qbo import account_ids, mapper
from app.qbo.client import QBOAPIError, QBONotConnectedError, QBOClient

NORMALIZED_COLLECTION = "normalized_transactions"


def sync_eligible_query(threshold: float, batch_id: str | None = None) -> dict:
    query = {
        "status": "ok",
        "qbo_sync_status": {"$nin": ["synced", "linked"]},
        "$or": [
            {"classification_status": {"$in": ["reviewed", "corrected"]}},
            {"classification_status": "auto", "classification_confidence": {"$gte": threshold}},
        ],
    }
    if batch_id:
        query["batch_id"] = batch_id
    return query


def _mark(db: Database, txn_id: str, status: str, qbo_txn_id: str | None = None, error: str | None = None) -> None:
    db[NORMALIZED_COLLECTION].update_one(
        {"id": txn_id},
        {
            "$set": {
                "qbo_sync_status": status,
                "qbo_txn_id": qbo_txn_id,
                "qbo_sync_error": error,
                "qbo_synced_at": datetime.now(timezone.utc).isoformat() if status in {"synced", "linked"} else None,
            }
        },
    )


def _find_transfer_pair(db: Database, txn: dict) -> dict | None:
    return db[NORMALIZED_COLLECTION].find_one(
        {
            "transaction_type": "transfer",
            "transaction_date": txn["transaction_date"],
            "amount": -txn["amount"],
            "bank_account": txn["counterparty"],
        }
    )


def _sync_non_transfer(db: Database, client: QBOClient, txn: dict) -> None:
    payload = mapper.build_qbo_payload(txn, lambda code: account_ids.get_qbo_id(db, code))
    result = client.create_entity(payload.entity_type, payload.body)
    _mark(db, txn["id"], "synced", qbo_txn_id=result["Id"])


def _sync_transfer_debit_leg(db: Database, client: QBOClient, txn: dict) -> None:
    from_id = account_ids.get_qbo_id(db, mapper.BANK_ACCOUNT_NO[txn["bank_account"]])
    to_id = account_ids.get_qbo_id(db, mapper.BANK_ACCOUNT_NO[txn["counterparty"]])
    payload = mapper.build_transfer_payload(txn, from_id, to_id)
    result = client.create_entity(payload.entity_type, payload.body)
    _mark(db, txn["id"], "synced", qbo_txn_id=result["Id"])

    pair = _find_transfer_pair(db, txn)
    if pair:
        _mark(db, pair["id"], "linked", qbo_txn_id=result["Id"])


def sync_pending(db: Database, settings: Settings | None = None, batch_id: str | None = None, client: QBOClient | None = None) -> dict:
    settings = settings or get_settings()
    client = client or QBOClient(db, settings)

    query = sync_eligible_query(settings.auto_sync_confidence_threshold, batch_id)
    pending = list(db[NORMALIZED_COLLECTION].find(query))

    non_transfers = [t for t in pending if t["transaction_type"] != "transfer"]
    transfer_debits = [t for t in pending if t["transaction_type"] == "transfer" and t["direction"] == "debit"]
    transfer_credits = [t for t in pending if t["transaction_type"] == "transfer" and t["direction"] == "credit"]

    synced = linked = failed = 0
    failures: list[dict] = []

    for txn in non_transfers:
        try:
            _sync_non_transfer(db, client, txn)
            synced += 1
        except QBONotConnectedError:
            raise
        except (QBOAPIError, mapper.UnmappableTransactionError, account_ids.AccountMappingError) as exc:
            _mark(db, txn["id"], "failed", error=str(exc))
            failed += 1
            failures.append({"transaction_id": txn["id"], "error": str(exc)})

    for txn in transfer_debits:
        try:
            _sync_transfer_debit_leg(db, client, txn)
            synced += 1
        except QBONotConnectedError:
            raise
        except (QBOAPIError, mapper.UnmappableTransactionError, account_ids.AccountMappingError) as exc:
            _mark(db, txn["id"], "failed", error=str(exc))
            failed += 1
            failures.append({"transaction_id": txn["id"], "error": str(exc)})

    for txn in transfer_credits:
        current = db[NORMALIZED_COLLECTION].find_one({"id": txn["id"]})
        if current["qbo_sync_status"] in {"synced", "linked"}:
            linked += 1  # already linked by its debit leg's own pass, above
            continue
        pair = _find_transfer_pair(db, txn)
        if pair and pair.get("qbo_sync_status") in {"synced", "linked"} and pair.get("qbo_txn_id"):
            _mark(db, txn["id"], "linked", qbo_txn_id=pair["qbo_txn_id"])
            linked += 1
        else:
            _mark(db, txn["id"], "failed", error="Waiting for the paired outgoing transfer leg to sync first.")
            failed += 1
            failures.append({"transaction_id": txn["id"], "error": "Waiting for paired outgoing leg."})

    return {"synced": synced, "linked": linked, "failed": failed, "failures": failures}
