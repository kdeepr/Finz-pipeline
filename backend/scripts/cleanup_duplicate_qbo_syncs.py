"""
One-off cleanup for a specific incident: an earlier sync run posted 195
Deposit/Purchase/Transfer entities into the sandbox, then a database reset
(the TESTING=true / mongomock bug - see git history) erased our local record
of having synced them, without undoing the postings themselves. A later
clean re-sync then posted the same 195 transactions again, so the sandbox
now has two copies of everything.

Every entity this app ever creates carries a PrivateNote of the form
"Finz sync | txn_id=<normalized_transactions id> | ...", so identifying an
orphan is exact, not fuzzy matching: pull every Deposit/Purchase/Transfer
from the sandbox, and any whose embedded txn_id no longer exists in the
current normalized_transactions collection is provably left over from a
sync run this database no longer has any record of - by construction, not
one of the transactions the app just synced.

Defaults to a dry run (lists what it would delete, does nothing). Pass
--confirm to actually delete. Run from backend/, with the same .env-backed
settings and Mongo the running app uses:

    python3 scripts/cleanup_duplicate_qbo_syncs.py            # dry run
    python3 scripts/cleanup_duplicate_qbo_syncs.py --confirm  # deletes
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import get_db  # noqa: E402
from app.qbo.client import QBOClient  # noqa: E402

ENTITY_TYPES = ["Deposit", "Purchase", "Transfer"]
PAGE_SIZE = 100
TXN_ID_RE = re.compile(r"Finz sync \| txn_id=([0-9a-fA-F-]+)")


def _fetch_all(client: QBOClient, entity_type: str) -> list[dict]:
    entities: list[dict] = []
    start = 1
    while True:
        result = client.query(f"SELECT * FROM {entity_type} STARTPOSITION {start} MAXRESULTS {PAGE_SIZE}")
        page = result.get("QueryResponse", {}).get(entity_type, [])
        entities.extend(page)
        if len(page) < PAGE_SIZE:
            return entities
        start += PAGE_SIZE


def find_orphans(db, client: QBOClient) -> dict[str, list[dict]]:
    orphans: dict[str, list[dict]] = {}
    for entity_type in ENTITY_TYPES:
        entities = _fetch_all(client, entity_type)
        found = []
        for entity in entities:
            note = entity.get("PrivateNote", "")
            match = TXN_ID_RE.search(note)
            if not match:
                continue  # not ours (e.g. sandbox sample data, or manually entered) - never touch it
            txn_id = match.group(1)
            if db["normalized_transactions"].find_one({"id": txn_id}) is None:
                found.append(entity)
        orphans[entity_type] = found
    return orphans


def _describe(entity_type: str, entity: dict) -> str:
    amount = entity.get("Amount") or (entity.get("Line", [{}])[0].get("Amount") if entity.get("Line") else "?")
    return f"  {entity_type} Id={entity['Id']} date={entity.get('TxnDate')} amount={amount}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="Actually delete. Without this flag, only lists what would be deleted.")
    args = parser.parse_args()

    settings = get_settings()
    db = get_db()
    client = QBOClient(db, settings)

    orphans = find_orphans(db, client)
    total = sum(len(v) for v in orphans.values())

    if total == 0:
        print("No orphaned entities found - nothing to clean up.")
        return

    print(f"Found {total} orphaned entities (posted by a sync this database has no record of):\n")
    for entity_type, entities in orphans.items():
        if not entities:
            continue
        print(f"{entity_type} ({len(entities)}):")
        for entity in entities:
            print(_describe(entity_type, entity))
        print()

    if not args.confirm:
        print("Dry run only - nothing was deleted. Re-run with --confirm to actually delete these.")
        return

    print("Deleting...")
    deleted = failed = 0
    for entity_type, entities in orphans.items():
        for entity in entities:
            try:
                client.delete_entity(entity_type.lower(), entity["Id"], entity["SyncToken"])
                deleted += 1
            except Exception as exc:  # noqa: BLE001 - report and keep going, don't abort the whole cleanup on one bad entity
                failed += 1
                print(f"  FAILED to delete {entity_type} Id={entity['Id']}: {exc}")

    print(f"\nDone: {deleted} deleted, {failed} failed.")


if __name__ == "__main__":
    main()
