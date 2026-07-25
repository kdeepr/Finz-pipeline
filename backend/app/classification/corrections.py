"""
Approved-correction store: when a reviewer corrects a transaction's
classification, we can save it against the transaction's pattern signature
(see signature.py) so every future transaction with the same shape - a
different job number, a different month - classifies the same way
automatically, without needing the reviewer to fix it again each time.

This is checked *before* the rule engine / Gemini in classification/service.py,
since a human's explicit correction should always outrank a generic rule.
"""
from pymongo.database import Database

from app.models.common import new_id, utcnow

COLLECTION = "classification_rules"


def get_rule(db: Database, signature: str) -> dict | None:
    return db[COLLECTION].find_one({"signature": signature}, {"_id": 0})


def upsert_rule(
    db: Database,
    signature: str,
    transaction_type: str,
    qbo_account: str | None,
    counterparty: str | None,
    example_description: str | None,
) -> dict:
    doc = {
        "signature": signature,
        "transaction_type": transaction_type,
        "qbo_account": qbo_account,
        "counterparty": counterparty,
        "example_description": example_description,
        "updated_at": utcnow().isoformat(),
    }
    existing = db[COLLECTION].find_one({"signature": signature})
    if existing:
        db[COLLECTION].update_one({"signature": signature}, {"$set": doc})
    else:
        doc["id"] = new_id()
        doc["created_at"] = doc["updated_at"]
        db[COLLECTION].insert_one(doc)
    return db[COLLECTION].find_one({"signature": signature}, {"_id": 0})


def list_rules(db: Database) -> list[dict]:
    return list(db[COLLECTION].find({}, {"_id": 0}))
