"""
Maps our chart-of-accounts "Account No." (e.g. "4000") to the QuickBooks
sandbox's own internal Account Id (e.g. "80") - these are NOT the same thing.

"4000" is just the AcctNum field we told you to type into QBO's account
creation form during 4.1; QBO assigns its own opaque Id to every account when
it's created, and every transaction line in the API must reference that Id,
not the account number. Since you created the chart of accounts by hand in
the sandbox, the only way to learn those Ids is to ask QBO for its Account
list and match each one back to our chart by AcctNum (falling back to Name,
since AcctNum is occasionally left blank if a field was skipped during setup).

This mapping is stored in Mongo (not re-fetched per transaction) and refreshed
via POST /api/qbo/accounts/sync - run that once after connecting, and again
any time an account is added or renamed in the sandbox.
"""
from pymongo.database import Database

COLLECTION = "qbo_account_ids"


class AccountMappingError(RuntimeError):
    pass


def store_mapping(db: Database, account_no: str, qbo_id: str, qbo_name: str) -> None:
    db[COLLECTION].update_one(
        {"account_no": account_no},
        {"$set": {"account_no": account_no, "qbo_id": qbo_id, "qbo_name": qbo_name}},
        upsert=True,
    )


def get_qbo_id(db: Database, account_no: str) -> str:
    doc = db[COLLECTION].find_one({"account_no": account_no})
    if doc is None:
        raise AccountMappingError(
            f"No QuickBooks account Id mapped for chart-of-accounts account '{account_no}'. "
            "Run POST /api/qbo/accounts/sync after connecting to QBO to build this mapping."
        )
    return doc["qbo_id"]


def build_mapping_from_qbo_accounts(db: Database, qbo_accounts: list[dict], our_chart: list[dict]) -> list[str]:
    """qbo_accounts: raw QBO Account query results. our_chart: data/reference/qbo_chart_of_accounts.json.
    Matches by AcctNum first, then falls back to case-insensitive Name match.
    Returns the list of our account_no values that could NOT be matched, so the
    caller can surface a clear error instead of silently leaving gaps.
    """
    by_acctnum = {a.get("AcctNum"): a for a in qbo_accounts if a.get("AcctNum")}
    by_name = {a["Name"].strip().lower(): a for a in qbo_accounts if a.get("Name")}

    unmatched = []
    for entry in our_chart:
        account_no = entry["Account No."]
        name = entry["Account Name"]
        match = by_acctnum.get(account_no) or by_name.get(name.strip().lower())
        if match is None:
            unmatched.append(account_no)
            continue
        store_mapping(db, account_no, match["Id"], match["Name"])
    return unmatched
