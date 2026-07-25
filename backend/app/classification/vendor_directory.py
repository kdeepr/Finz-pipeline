"""
Known-vendor directory for the *expense side* of the ledger.

Raw card/ACH merchant descriptors ("SHELL OIL 574221", "BP#98231 NEW YORK")
don't follow a regular shape the way customer-receipt memos do, so instead of
regexing them apart we look the merchant substring up in a directory - the
same approach real expense-categorization products (Plaid, Ramp, Brex) use
via merchant enrichment. A hit gives us the counterparty's clean name AND its
transaction type/QBO account in one lookup, since "this is Home Depot" already
implies "Materials & Supplies - COGS".

Stored in Mongo (seeded once from data/reference/vendor_directory.json) rather
than as Python if/elif branches, so recognizing a new vendor - or fixing a
miscategorized one - is a data change via the classification-rules API, not a
code change.
"""
import json
from pathlib import Path

from pymongo.database import Database

COLLECTION = "vendor_directory"

_SEED_PATH = Path(__file__).resolve().parents[3] / "data" / "reference" / "vendor_directory.json"


def seed_default_vendors(db: Database) -> None:
    if db[COLLECTION].count_documents({}) > 0:
        return
    with open(_SEED_PATH) as f:
        seed = json.load(f)
    for entry in seed:
        entry["match_substring"] = entry["match_substring"].upper()
    db[COLLECTION].insert_many(seed)


def lookup_vendor(db: Database, description_upper: str) -> dict | None:
    """Longest-substring-match wins, so a more specific entry (e.g. "APEX ELEC LLC")
    beats a shorter one that might otherwise coincidentally match."""
    candidates = [v for v in db[COLLECTION].find({}) if v["match_substring"] in description_upper]
    if not candidates:
        return None
    return max(candidates, key=lambda v: len(v["match_substring"]))


def upsert_vendor(
    db: Database,
    match_substring: str,
    canonical_name: str,
    transaction_type: str,
    qbo_account_code: str,
) -> None:
    db[COLLECTION].update_one(
        {"match_substring": match_substring.upper()},
        {
            "$set": {
                "match_substring": match_substring.upper(),
                "canonical_name": canonical_name,
                "transaction_type": transaction_type,
                "qbo_account_code": qbo_account_code,
            }
        },
        upsert=True,
    )
