"""
Bank account canonicalization: maps whatever free-text account name/label a
bank export uses to one of the company's actual bank accounts on the balance
sheet (Operating Checking / Tax Reserve, per the QBO chart of accounts).

This lives in Mongo, not in an if/elif chain, so recognizing a new bank's
naming convention (or a second real bank account added later) is a data change
via the API, not a code change.
"""
from pymongo.database import Database

COLLECTION = "bank_account_aliases"

# Seed aliases derived from data/reference/qbo_chart_of_accounts.json (accounts
# 1000 and 1010) plus a few common variants a real bank statement might use.
DEFAULT_ALIASES = {
    "Operating Checking": [
        "operating checking",
        "checking",
        "operating account",
        "op checking",
    ],
    "Tax Reserve": [
        "tax reserve",
        "savings",
        "tax savings",
    ],
}


def seed_default_aliases(db: Database) -> None:
    col = db[COLLECTION]
    if col.count_documents({}) > 0:
        return
    docs = []
    for canonical, aliases in DEFAULT_ALIASES.items():
        docs.append({"alias": canonical.lower(), "canonical_name": canonical})
        for alias in aliases:
            docs.append({"alias": alias.lower(), "canonical_name": canonical})
    col.insert_many(docs)


def resolve_bank_account(db: Database, raw_value: str | None) -> str | None:
    if not raw_value or not raw_value.strip():
        return None
    match = db[COLLECTION].find_one({"alias": raw_value.strip().lower()})
    return match["canonical_name"] if match else None


def add_alias(db: Database, alias: str, canonical_name: str) -> None:
    db[COLLECTION].update_one(
        {"alias": alias.strip().lower()},
        {"$set": {"alias": alias.strip().lower(), "canonical_name": canonical_name}},
        upsert=True,
    )


def list_known_accounts(db: Database) -> list[str]:
    return sorted(set(doc["canonical_name"] for doc in db[COLLECTION].find({})))
