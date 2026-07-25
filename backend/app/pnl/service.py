"""
Cash-basis P&L computation (PDF 4.4). Always computed live from the current
state of normalized_transactions rather than a stored snapshot - if a reviewer
corrects a classification tomorrow, the P&L reflects it immediately without a
separate "regenerate" step.

Section grouping (Revenue / COGS / Operating Expenses) comes straight from
each account's "QBO Account Type" in the chart of accounts (Income / Cost of
Goods Sold / Expenses) - the same grouping QuickBooks itself uses, which is
what makes the 4.6 reconciliation an apples-to-apples comparison later.

Exclusions happen structurally, not as a special case here: transfers, owner
activity, and fixed-asset purchases were already excluded by not having a
PNL_ELIGIBLE transaction_type (see pnl/periods.py), and duplicates were
already excluded by never getting a transaction_type in the first place
(status="duplicate" transactions are never classified - see
classification/service.py).
"""
from pymongo.database import Database

from app.classification.coa import accounts_by_code
from app.models.common import utcnow
from app.models.pnl import PnLAccountLine, PnLSection, PnLStatement
from app.pnl.periods import PNL_ELIGIBLE_TYPES, period_bounds, period_label

_SECTION_BY_QBO_TYPE = {
    "Income": "revenue",
    "Cost of Goods Sold": "cogs",
    "Expenses": "operating_expenses",
}


def _build_section(lines_by_account: dict[str, dict]) -> PnLSection:
    accounts = accounts_by_code()
    lines = [
        PnLAccountLine(
            account_code=code,
            account_name=accounts.get(code, {}).get("Account Name", code),
            total=round(agg["total"], 2),
            transaction_count=agg["count"],
        )
        for code, agg in lines_by_account.items()
    ]
    lines.sort(key=lambda line: line.account_code)
    subtotal = round(sum(line.total for line in lines), 2)
    return PnLSection(lines=lines, subtotal=subtotal)


def compute_pnl(db: Database, period: str) -> PnLStatement:
    start, end = period_bounds(db, period)
    accounts = accounts_by_code()

    query = {
        "status": "ok",
        "transaction_type": {"$in": PNL_ELIGIBLE_TYPES},
        "transaction_date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
    }

    section_data: dict[str, dict[str, dict]] = {"revenue": {}, "cogs": {}, "operating_expenses": {}}

    for txn in db["normalized_transactions"].find(query):
        code = txn.get("qbo_account")
        account = accounts.get(code) if code else None
        if account is None:
            # A PNL_ELIGIBLE transaction type should always carry a valid account
            # (rules/Gemini/review all validate this) - if one somehow doesn't,
            # skip it rather than crash the report; it still counts below.
            continue
        section = _SECTION_BY_QBO_TYPE.get(account["QBO Account Type"])
        if section is None:
            continue
        bucket = section_data[section].setdefault(code, {"total": 0.0, "count": 0})
        bucket["total"] += txn["amount"]
        bucket["count"] += 1

    # "ok" transactions in this period that haven't been classified yet aren't
    # silently dropped from view - they're surfaced as a count so the P&L is
    # explicit about what it does *not* yet include, instead of looking
    # deceptively complete.
    unclassified_count = db["normalized_transactions"].count_documents(
        {
            "status": "ok",
            "transaction_type": {"$nin": PNL_ELIGIBLE_TYPES + ["transfer", "owner_activity", "fixed_asset"]},
            "transaction_date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }
    )

    revenue = _build_section(section_data["revenue"])
    cogs = _build_section(section_data["cogs"])
    opex = _build_section(section_data["operating_expenses"])

    gross_profit = round(revenue.subtotal + cogs.subtotal, 2)
    net_profit = round(gross_profit + opex.subtotal, 2)

    return PnLStatement(
        period=period,
        period_label=period_label(period, start, end),
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        operating_expenses=opex,
        net_profit=net_profit,
        excluded_unclassified_count=unclassified_count,
        generated_at=utcnow().isoformat(),
    )


def transactions_for_line(db: Database, period: str, account_code: str) -> list[dict]:
    start, end = period_bounds(db, period)
    query = {
        "status": "ok",
        "qbo_account": account_code,
        "transaction_type": {"$in": PNL_ELIGIBLE_TYPES},
        "transaction_date": {"$gte": start.isoformat(), "$lte": end.isoformat()},
    }
    return list(db["normalized_transactions"].find(query, {"_id": 0}).sort("transaction_date", 1))
