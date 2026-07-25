"""
Duplicate detection against everything already ingested - not just the current
file - because the PDF explicitly calls out duplicates "created by overlapping
source files" (e.g. a bank's "last 30 days" export re-sends transactions an
earlier monthly export already contained).

The dedup key itself is computed in normalizer.compute_dedup_key: the bank's
own transaction ID when we have one, otherwise a content hash of date/amount/
account/description. This module only does the lookup, so the ingestion
service can insert-then-check row by row and catch duplicates both across
batches and within a single batch (e.g. a file that repeats a row twice).
"""
from pymongo.database import Database

COLLECTION = "normalized_transactions"


def find_existing_by_dedup_key(db: Database, dedup_key: str) -> dict | None:
    return db[COLLECTION].find_one({"dedup_key": dedup_key, "status": {"$ne": "duplicate"}})
