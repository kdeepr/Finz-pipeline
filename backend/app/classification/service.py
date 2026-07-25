"""
Classification orchestration for one transaction, in priority order:

1. Approved-correction store (a human already told us how this exact pattern
   should classify) - highest priority, always wins.
2. Deterministic rule engine (transfers/owner activity/refunds/vendor
   directory/revenue sub-typing) - free and fully explainable.
3. Gemini, only if configured - last resort for whatever the rules can't
   resolve.
4. Otherwise: left "unclassified" with confidence 0, visible in the review
   queue rather than silently skipped.

Never touches a transaction a human already reviewed/corrected - re-running
classification must not undo a person's decision.
"""
from pymongo.database import Database

from app.classification import corrections
from app.classification.coa import account_name
from app.classification.counterparty import extract_counterparty
from app.classification.gemini_classifier import classify_with_gemini
from app.classification.rules import ClassificationResult, classify_by_rules
from app.classification.signature import compute_signature
from app.config import Settings, get_settings

NORMALIZED_COLLECTION = "normalized_transactions"

LOCKED_STATUSES = {"reviewed", "corrected"}


def classify_transaction(db: Database, txn: dict, settings: Settings | None = None) -> dict:
    if txn.get("classification_status") in LOCKED_STATUSES:
        return txn
    if txn.get("status") != "ok":
        return txn

    settings = settings or get_settings()
    description = txn.get("description_normalized")
    direction = txn.get("direction")
    bank_account = txn.get("bank_account")
    amount = txn.get("amount")

    signature = compute_signature(description, direction)
    learned = corrections.get_rule(db, signature)

    if learned:
        result = ClassificationResult(
            transaction_type=learned["transaction_type"],
            qbo_account=learned["qbo_account"],
            counterparty=learned["counterparty"],
            confidence=1.0,
            explanation=(
                f"Matches a previously approved correction pattern (example: "
                f"'{learned.get('example_description')}')."
            ),
            source="learned_rule",
        )
    else:
        result = classify_by_rules(db, description, direction, bank_account)
        if result is None and settings.gemini_api_key:
            result = classify_with_gemini(settings, description or "", amount or 0.0, direction or "", bank_account or "")

    update = {"updated_at": txn.get("updated_at")}
    if result is None:
        update.update(
            {
                "transaction_type": "uncategorized",
                "qbo_account": None,
                "qbo_account_name": None,
                "counterparty": extract_counterparty(description),
                "classification_confidence": 0.0,
                "classification_explanation": "No rule, vendor-directory, or Gemini match; needs manual classification.",
                "classification_status": "unclassified",
                "classification_source": None,
            }
        )
    else:
        update.update(
            {
                "transaction_type": result.transaction_type,
                "qbo_account": result.qbo_account,
                "qbo_account_name": account_name(result.qbo_account) if result.qbo_account else None,
                "counterparty": result.counterparty,
                "classification_confidence": result.confidence,
                "classification_explanation": result.explanation,
                "classification_status": "auto",
                "classification_source": result.source,
            }
        )

    db[NORMALIZED_COLLECTION].update_one({"id": txn["id"]}, {"$set": update})
    txn.update(update)
    return txn


def classify_pending(db: Database, batch_id: str | None = None) -> dict:
    query: dict = {"status": "ok", "classification_status": {"$nin": list(LOCKED_STATUSES)}}
    if batch_id:
        query["batch_id"] = batch_id

    settings = get_settings()
    counts: dict[str, int] = {}
    total = 0
    for txn in db[NORMALIZED_COLLECTION].find(query):
        classify_transaction(db, txn, settings)
        total += 1
        key = txn.get("transaction_type") or "uncategorized"
        counts[key] = counts.get(key, 0) + 1

    return {"classified": total, "by_transaction_type": counts}


def apply_review(
    db: Database,
    txn: dict,
    transaction_type: str,
    qbo_account: str | None,
    counterparty: str | None,
    apply_to_similar: bool,
) -> dict:
    was_auto_correct = (
        txn.get("transaction_type") == transaction_type
        and txn.get("qbo_account") == qbo_account
        and txn.get("counterparty") == counterparty
    )
    new_status = "reviewed" if was_auto_correct else "corrected"

    update = {
        "transaction_type": transaction_type,
        "qbo_account": qbo_account,
        "qbo_account_name": account_name(qbo_account) if qbo_account else None,
        "counterparty": counterparty,
        "classification_status": new_status,
        "classification_source": "user",
        "classification_confidence": 1.0,
        "classification_explanation": "Manually reviewed and approved." if was_auto_correct else "Manually corrected by reviewer.",
    }
    db[NORMALIZED_COLLECTION].update_one({"id": txn["id"]}, {"$set": update})
    txn.update(update)

    if apply_to_similar:
        signature = compute_signature(txn.get("description_normalized"), txn.get("direction"))
        corrections.upsert_rule(
            db,
            signature=signature,
            transaction_type=transaction_type,
            qbo_account=qbo_account,
            counterparty=counterparty,
            example_description=txn.get("description_raw"),
        )

    return txn
