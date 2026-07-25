"""Pulls the sandbox's real Account list and builds the account_no -> QBO Id mapping (see account_ids.py)."""
from pymongo.database import Database

from app.classification.coa import load_chart_of_accounts
from app.qbo.account_ids import build_mapping_from_qbo_accounts
from app.qbo.client import QBOClient


def sync_account_ids(db: Database, client: QBOClient) -> list[str]:
    result = client.query("SELECT * FROM Account")
    qbo_accounts = result.get("QueryResponse", {}).get("Account", [])
    our_chart = load_chart_of_accounts()
    return build_mapping_from_qbo_accounts(db, qbo_accounts, our_chart)
