"""
Reconciliation (PDF 4.6): pulls QuickBooks' own cash-basis P&L for the same
period, parses it, and compares it line-by-line against our internally
generated P&L (app/pnl/service.py) - the same report used in the app's own
P&L view, not a separately maintained number.

Matching an account between the two systems prefers the QBO account Id (via
the account_no <-> qbo_id mapping built in 4.5's accounts/sync step) since
that's unambiguous; it falls back to a case-insensitive name match for any
account QBO reports on that wasn't in our mapping-eligible chart (which
shouldn't normally happen, but should never crash a reconciliation run if it
does - it just surfaces as a line worth a human's attention instead).

A clean "sync succeeded" is explicitly not the bar (PDF 4.6: "a successful API
sync is not sufficient"). This report is what proves the categorization and
the QBO postings actually agree on real dollar amounts, account by account.
"""
from pymongo.database import Database

from app.classification.coa import load_chart_of_accounts
from app.config import Settings, get_settings
from app.models.common import utcnow
from app.models.reconciliation import ReconciliationLine, ReconciliationReport
from app.pnl.periods import period_bounds, period_label
from app.pnl.service import compute_pnl
from app.qbo.account_ids import get_account_no_by_qbo_id
from app.qbo.client import QBOClient
from app.reconciliation.qbo_report_parser import parse_profit_and_loss

TOLERANCE = 0.01

# QuickBooks' own P&L report shows Cost of Goods Sold and Expenses account
# balances as positive figures (to be subtracted to reach Net Income); this
# app stores every outflow as a negative amount (the same bank-debit
# convention used everywhere else in this codebase, including its own P&L).
# Without normalizing to one sign convention here, every correctly-synced
# COGS/Expense account would show as a "mismatch" purely from this
# report-display difference, not an actual discrepancy.
EXPENSE_SECTION_TYPES = {"Cost of Goods Sold", "Expenses"}


def _resolve_account_code(db: Database, row: dict, chart_by_name: dict[str, str]) -> str | None:
    if row.get("qbo_account_id"):
        code = get_account_no_by_qbo_id(db, row["qbo_account_id"])
        if code:
            return code
    return chart_by_name.get(row["account_name"].strip().lower())


def reconcile(db: Database, period: str, settings: Settings | None = None, client: QBOClient | None = None) -> ReconciliationReport:
    settings = settings or get_settings()
    client = client or QBOClient(db, settings)

    pnl = compute_pnl(db, period)
    start, end = period_bounds(db, period)

    raw_report = client.get_profit_and_loss(start.isoformat(), end.isoformat())
    parsed = parse_profit_and_loss(raw_report)

    chart = load_chart_of_accounts()
    chart_by_name = {a["Account Name"].strip().lower(): a["Account No."] for a in chart}
    account_types = {a["Account No."]: a["QBO Account Type"] for a in chart}

    app_by_code: dict[str, dict] = {}
    for section in (pnl.revenue, pnl.cogs, pnl.operating_expenses):
        for line in section.lines:
            app_by_code[line.account_code] = {"account_name": line.account_name, "amount": line.total}

    qbo_by_code: dict[str, dict] = {}
    for row in parsed["accounts"]:
        code = _resolve_account_code(db, row, chart_by_name)
        amount = row["amount"]
        if code and account_types.get(code) in EXPENSE_SECTION_TYPES:
            amount = -amount
        key = code or f"unmatched:{row['account_name']}"
        existing = qbo_by_code.get(key, {"account_name": row["account_name"], "amount": 0.0})
        existing["amount"] += amount
        qbo_by_code[key] = existing

    all_codes = set(app_by_code) | set(qbo_by_code)
    lines: list[ReconciliationLine] = []
    for code in sorted(all_codes, key=str):
        app_entry = app_by_code.get(code)
        qbo_entry = qbo_by_code.get(code)
        app_amount = round(app_entry["amount"], 2) if app_entry else 0.0
        qbo_amount = round(qbo_entry["amount"], 2) if qbo_entry else 0.0
        account_name = (app_entry or qbo_entry)["account_name"]
        difference = round(app_amount - qbo_amount, 2)
        is_unmatched_code = code.startswith("unmatched:")

        if app_entry is None:
            status, explanation = "qbo_only", "QuickBooks reports activity on this account that isn't in the app's P&L."
        elif qbo_entry is None:
            status, explanation = "app_only", "The app classified transactions to this account, but QuickBooks shows no activity - check whether they were synced."
        elif is_unmatched_code:
            status, explanation = (
                "mismatch",
                "Could not confidently match this QuickBooks report line to one of our chart-of-accounts codes.",
            )
        elif abs(difference) <= TOLERANCE:
            status, explanation = "match", "Amounts agree."
        else:
            status, explanation = (
                "mismatch",
                f"App shows {app_amount:.2f}, QuickBooks shows {qbo_amount:.2f} - review transactions on this account for missed or duplicate syncs.",
            )

        lines.append(
            ReconciliationLine(
                account_code=None if is_unmatched_code else code,
                account_name=account_name,
                app_amount=app_amount,
                qbo_amount=qbo_amount,
                difference=difference,
                status=status,
                explanation=explanation,
            )
        )

    qbo_net_profit = round(parsed["section_totals"].get("NetIncome", 0.0), 2)
    net_profit_difference = round(pnl.net_profit - qbo_net_profit, 2)
    overall_status = (
        "reconciled"
        if all(line.status == "match" for line in lines) and abs(net_profit_difference) <= TOLERANCE
        else "discrepancies_found"
    )

    return ReconciliationReport(
        period=period,
        period_label=period_label(period, start, end),
        lines=lines,
        app_net_profit=pnl.net_profit,
        qbo_net_profit=qbo_net_profit,
        net_profit_difference=net_profit_difference,
        overall_status=overall_status,
        generated_at=utcnow().isoformat(),
    )
