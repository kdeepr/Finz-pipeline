"""
Tests find_orphans() from scripts/cleanup_duplicate_qbo_syncs.py: an entity
is an orphan only if it carries our own "txn_id=<id>" PrivateNote AND that id
no longer exists in normalized_transactions. Anything without our PrivateNote
marker (sandbox sample data, manually entered transactions) must never be
touched, regardless of how it looks otherwise.
"""
from app.config import Settings
from app.db import get_db
from app.qbo import connection_store
from app.qbo.client import QBOClient
from scripts.cleanup_duplicate_qbo_syncs import find_orphans


class FakeResponse:
    def __init__(self, json_data):
        self.status_code = 200
        self._json_data = json_data
        self.text = str(json_data)

    def json(self):
        return self._json_data


class FakeQueryTransport:
    def __init__(self, by_entity_type: dict[str, list[dict]]):
        self.by_entity_type = by_entity_type

    def get(self, url, params=None, headers=None, timeout=None):
        query = params["query"]
        entity_type = query.split("FROM ")[1].split(" ")[0]
        start = int(query.split("STARTPOSITION ")[1].split(" ")[0])
        page = self.by_entity_type.get(entity_type, [])[start - 1 : start - 1 + 100]
        return FakeResponse({"QueryResponse": {entity_type: page}})


def _settings():
    return Settings(qbo_client_id="id", qbo_client_secret="secret", qbo_environment="sandbox", testing=True)


def _entity(entity_id, txn_id=None, sync_token="0"):
    note = f"Finz sync | txn_id={txn_id} | Acme" if txn_id else "Some other note"
    return {"Id": entity_id, "SyncToken": sync_token, "PrivateNote": note, "TxnDate": "2026-04-01", "Amount": 100.0}


def test_orphan_is_an_entity_whose_txn_id_no_longer_exists_locally():
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    db["normalized_transactions"].insert_one({"id": "aaaaaaaa-1111-4444-8888-000000000001"})

    by_type = {
        "Deposit": [
            _entity("1", txn_id="aaaaaaaa-1111-4444-8888-000000000001"),
            _entity("2", txn_id="bbbbbbbb-2222-4444-8888-000000000002"),
        ],
        "Purchase": [],
        "Transfer": [],
    }
    client = QBOClient(db, _settings(), transport=FakeQueryTransport(by_type))

    orphans = find_orphans(db, client)

    assert [e["Id"] for e in orphans["Deposit"]] == ["2"]
    assert orphans["Purchase"] == []
    assert orphans["Transfer"] == []


def test_entities_without_our_private_note_are_never_flagged():
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)

    by_type = {"Deposit": [_entity("99", txn_id=None)], "Purchase": [], "Transfer": []}
    client = QBOClient(db, _settings(), transport=FakeQueryTransport(by_type))

    orphans = find_orphans(db, client)

    assert orphans["Deposit"] == []
