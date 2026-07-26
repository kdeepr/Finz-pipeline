"""Pulls the sandbox's real Account list and builds the account_no -> QBO Id mapping (see account_ids.py)."""
from pymongo.database import Database

from app.classification.coa import load_chart_of_accounts
from app.qbo.account_ids import build_mapping_from_qbo_accounts
from app.qbo.client import QBOClient

PAGE_SIZE = 100


def _fetch_all_accounts(client: QBOClient) -> list[dict]:
    # A new QBO company (even an empty sandbox) starts with dozens of
    # built-in default accounts, so once a real chart of accounts is added
    # on top, the total easily crosses QBO's per-query page size - a single
    # unpaginated "SELECT * FROM Account" then silently drops whichever
    # accounts fall past position 100, matching some but not all of ours for
    # no apparent reason. STARTPOSITION/MAXRESULTS paging until a
    # short/empty page comes back is the documented way to get the full list.
    accounts: list[dict] = []
    start = 1
    while True:
        result = client.query(f"SELECT * FROM Account STARTPOSITION {start} MAXRESULTS {PAGE_SIZE}")
        page = result.get("QueryResponse", {}).get("Account", [])
        accounts.extend(page)
        if len(page) < PAGE_SIZE:
            return accounts
        start += PAGE_SIZE


def sync_account_ids(db: Database, client: QBOClient) -> list[str]:
    qbo_accounts = _fetch_all_accounts(client)
    our_chart = load_chart_of_accounts()
    return build_mapping_from_qbo_accounts(db, qbo_accounts, our_chart)
