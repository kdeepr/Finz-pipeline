"""
Parses QuickBooks Online's ProfitAndLoss report response into a flat list of
(account_name, qbo_account_id, amount) rows plus the report's own Net Income
figure.

QBO's report JSON is a recursive tree of Row objects - each "Section" (Income,
COGS, Expenses, ...) contains either more Sections or "Data" rows (one per
account with a balance), plus a "Summary" row with that section's subtotal.
This walks the whole tree once, so it works regardless of how QuickBooks
nests things for a given company's report customization.

This is the one integration point that can't be validated against a live
report from this environment (see connect_flow.md) - it's written against
Intuit's documented report shape and covered by unit tests using a fabricated
report matching that shape; a real report should be spot-checked once you
have sandbox access (GET /api/reconciliation/{period} surfaces the raw QBO
report alongside the parsed comparison for exactly that purpose).
"""
import re

_LEADING_ACCOUNT_NUMBER_RE = re.compile(r"^\d+\s+")


def _clean_account_name(raw_name: str) -> str:
    """Strips a leading account-number prefix QBO adds when the company has
    "Show account numbers" enabled in report preferences, e.g. "4000 Repair
    Service Revenue" -> "Repair Service Revenue"."""
    return _LEADING_ACCOUNT_NUMBER_RE.sub("", raw_name).strip()


def _to_float(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def _walk_rows(rows: list[dict], data_rows: list[dict], section_totals: dict[str, float]) -> None:
    for row in rows:
        row_type = row.get("type")
        if row_type == "Data":
            col_data = row.get("ColData", [])
            if len(col_data) < 2:
                continue
            data_rows.append(
                {
                    "account_name": _clean_account_name(col_data[0].get("value", "")),
                    "qbo_account_id": col_data[0].get("id"),
                    "amount": _to_float(col_data[-1].get("value")),
                }
            )
        elif row_type == "Section":
            group = row.get("group")
            # A parent account with sub-accounts (e.g. "Utilities" over "Gas
            # and Electric"/"Telephone") reports its own direct postings as a
            # Section's Header, not a Data row - skipping it silently drops
            # any amount posted straight to the parent account itself, even
            # though it's exactly as real as a plain Data row's amount.
            #
            # Only do this for a NESTED parent-account section, though -
            # every top-level report section (Income/COGS/Expenses/...) also
            # carries a Header, but that's just its own section title
            # ("Income", "Expenses", ...), not an account. Top-level sections
            # are the ones with a "group" key; a nested parent-account isn't.
            if not group:
                header = row.get("Header", {}).get("ColData", [])
                if len(header) >= 2:
                    data_rows.append(
                        {
                            "account_name": _clean_account_name(header[0].get("value", "")),
                            "qbo_account_id": header[0].get("id"),
                            "amount": _to_float(header[-1].get("value")),
                        }
                    )
            nested = row.get("Rows", {}).get("Row", [])
            if nested:
                _walk_rows(nested, data_rows, section_totals)
            summary = row.get("Summary", {}).get("ColData", [])
            if group and len(summary) >= 2:
                section_totals[group] = _to_float(summary[-1].get("value"))


def parse_profit_and_loss(report: dict) -> dict:
    """Returns {"accounts": [{"account_name", "qbo_account_id", "amount"}, ...],
    "section_totals": {"Income": x, "COGS": x, "Expenses": x, "NetIncome": x, ...}}"""
    rows = report.get("Rows", {}).get("Row", [])
    data_rows: list[dict] = []
    section_totals: dict[str, float] = {}
    _walk_rows(rows, data_rows, section_totals)
    return {"accounts": data_rows, "section_totals": section_totals}
