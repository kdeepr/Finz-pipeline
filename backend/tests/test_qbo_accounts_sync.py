"""
sync_account_ids pages through QBO's Account query rather than trusting a
single unpaginated call to return everything - a real sandbox easily has
100+ accounts once QBO's built-in defaults are combined with a real chart
of accounts, and QBO's query API caps a single page at PAGE_SIZE results.
"""
from app.config import Settings
from app.db import get_db
from app.qbo import connection_store
from app.qbo.account_ids import get_qbo_id
from app.qbo.accounts_sync import PAGE_SIZE, _fetch_all_accounts
from app.qbo.client import QBOClient


class FakeResponse:
    def __init__(self, json_data):
        self.status_code = 200
        self._json_data = json_data
        self.text = str(json_data)

    def json(self):
        return self._json_data


class PagingTransport:
    """Simulates QBO's STARTPOSITION/MAXRESULTS paging over a fixed account list."""

    def __init__(self, all_accounts):
        self.all_accounts = all_accounts
        self.queries = []

    def get(self, url, params=None, headers=None, timeout=None):
        query = params["query"]
        self.queries.append(query)
        start = int(query.split("STARTPOSITION ")[1].split(" ")[0])
        page = self.all_accounts[start - 1 : start - 1 + PAGE_SIZE]
        return FakeResponse({"QueryResponse": {"Account": page}})

    def post(self, *a, **k):
        raise AssertionError("accounts sync should not POST")


def _settings():
    return Settings(qbo_client_id="id", qbo_client_secret="secret", qbo_environment="sandbox", testing=True)


def test_paginates_past_the_first_page_to_find_every_account():
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)

    filler = [{"Id": str(i), "Name": f"Default Account {i}", "AcctNum": None} for i in range(PAGE_SIZE)]
    real_account = {"Id": "999", "Name": "Utilities", "AcctNum": "6060"}
    transport = PagingTransport(filler + [real_account])
    client = QBOClient(db, _settings(), transport=transport)

    from app.qbo.account_ids import build_mapping_from_qbo_accounts

    qbo_accounts = _fetch_all_accounts(client)
    assert len(qbo_accounts) == PAGE_SIZE + 1  # would be PAGE_SIZE without pagination - "Utilities" lost

    our_chart = [{"Account No.": "6060", "Account Name": "Utilities"}]
    unmatched = build_mapping_from_qbo_accounts(db, qbo_accounts, our_chart)
    assert unmatched == []
    assert get_qbo_id(db, "6060") == "999"
    assert len(transport.queries) == 2  # confirms it actually paged, not a lucky single call


def test_single_short_page_does_not_trigger_a_second_query():
    db = get_db()
    connection_store.save_tokens(db, "realm-1", "at", "rt", 3600)
    transport = PagingTransport([{"Id": "1", "Name": "Utilities", "AcctNum": "6060"}])
    client = QBOClient(db, _settings(), transport=transport)

    accounts = _fetch_all_accounts(client)
    assert len(accounts) == 1
    assert len(transport.queries) == 1
