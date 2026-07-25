"""
Reconciliation tests using a FakeQBOClient whose get_profit_and_loss() returns
a fabricated report (there's no live sandbox to pull a real one from in this
environment - see connect_flow.md). The fixture numbers for the "perfect
match" case are copied directly from this app's own /api/pnl/2026-04 output
for the fully-ingested dataset, so the test proves the comparison logic
itself is correct, not just that two hardcoded numbers happen to agree.
"""
import io
from pathlib import Path

from app.classification.coa import load_chart_of_accounts
from app.db import get_db
from app.qbo.account_ids import build_mapping_from_qbo_accounts
from app.qbo.connection_store import save_tokens
from app.reconciliation.service import reconcile

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "sample_bank_exports"
ALL_SOURCE_FILES = [
    "operating_checking_2026_04.csv",
    "operating_checking_2026_05.csv",
    "operating_checking_2026_06.csv",
    "tax_reserve_2026_04.csv",
    "tax_reserve_2026_05.csv",
    "tax_reserve_2026_06.csv",
    "operating_checking_2026_04_15_to_2026_05_15.csv",
    "operating_checking_2026_05_15_to_2026_06_15.csv",
    "operating_checking_2026_06_10_to_2026_07_10.csv",
]

# Copied verbatim from GET /api/pnl/2026-04 against the fully ingested dataset.
APRIL_LINES = {
    "4000": ("Repair Service Revenue", 42775.0),
    "4010": ("Installation Revenue", 53000.0),
    "4020": ("Maintenance Plan Revenue", 3650.0),
    "4100": ("Customer Refunds", -1250.0),
    "5000": ("Materials & Supplies", -15025.0),
    "5010": ("Subcontractor Costs", -16300.0),
    "6000": ("Payroll Expense", -25800.0),
    "6010": ("Rent Expense", -8200.0),
    "6020": ("Vehicle & Fuel", -1485.0),
    "6030": ("Software & Subscriptions", -1445.0),
    "6040": ("Marketing & Advertising", -2800.0),
    "6050": ("Insurance Expense", -1225.0),
    "6060": ("Utilities", -1170.0),
    "6070": ("Professional Fees", -1650.0),
    "6080": ("Bank Fees", -35.0),
    "6090": ("Office & General", -310.0),
    "6100": ("Repairs & Maintenance", -740.0),
}
APRIL_NET_PROFIT = 21990.0


class FakeQBOClient:
    def __init__(self, report: dict):
        self._report = report

    def get_profit_and_loss(self, start_date, end_date):
        return self._report


def _data_row(account_no, name, amount, qbo_id):
    return {"type": "Data", "ColData": [{"value": name, "id": qbo_id}, {"value": f"{amount:.2f}"}]}


def _build_report(lines: dict[str, tuple], net_income: float):
    income_rows = [_data_row(c, n, a, f"id-{c}") for c, (n, a) in lines.items() if c.startswith("4")]
    cogs_rows = [_data_row(c, n, a, f"id-{c}") for c, (n, a) in lines.items() if c.startswith("5")]
    expense_rows = [_data_row(c, n, a, f"id-{c}") for c, (n, a) in lines.items() if c.startswith("6")]
    return {
        "Rows": {
            "Row": [
                {"type": "Section", "group": "Income", "Rows": {"Row": income_rows}, "Summary": {"ColData": [{"value": "Total Income"}, {"value": "0"}]}},
                {"type": "Section", "group": "COGS", "Rows": {"Row": cogs_rows}, "Summary": {"ColData": [{"value": "Total COGS"}, {"value": "0"}]}},
                {"type": "Section", "group": "Expenses", "Rows": {"Row": expense_rows}, "Summary": {"ColData": [{"value": "Total Expenses"}, {"value": "0"}]}},
                {"type": "Section", "group": "NetIncome", "Summary": {"ColData": [{"value": "Net Income"}, {"value": f"{net_income:.2f}"}]}},
            ]
        }
    }


def _setup(client):
    profile_id = client.get("/api/column-mappings").json()[0]["id"]
    for filename in ALL_SOURCE_FILES:
        content = (DATA_DIR / filename).read_bytes()
        client.post("/api/uploads", files={"file": (filename, io.BytesIO(content), "text/csv")}, data={"mapping_profile_id": profile_id})
    client.post("/api/classification/run")

    db = get_db()
    save_tokens(db, realm_id="fake-realm", access_token="x", refresh_token="y", expires_in=3600)
    qbo_accounts = [{"Id": f"id-{a['Account No.']}", "Name": a["Account Name"], "AcctNum": a["Account No."]} for a in load_chart_of_accounts()]
    build_mapping_from_qbo_accounts(db, qbo_accounts, load_chart_of_accounts())
    return db


def test_reconciliation_reports_reconciled_when_amounts_agree(client):
    db = _setup(client)
    report = _build_report(APRIL_LINES, APRIL_NET_PROFIT)
    result = reconcile(db, "2026-04", client=FakeQBOClient(report))

    assert result.overall_status == "reconciled"
    assert result.app_net_profit == APRIL_NET_PROFIT
    assert result.qbo_net_profit == APRIL_NET_PROFIT
    assert result.net_profit_difference == 0.0
    assert all(line.status == "match" for line in result.lines)
    assert len(result.lines) == len(APRIL_LINES)


def test_reconciliation_flags_a_genuine_mismatch(client):
    db = _setup(client)
    tampered = dict(APRIL_LINES)
    tampered["6010"] = ("Rent Expense", -9000.0)  # QBO shows a different rent figure than the app
    report = _build_report(tampered, APRIL_NET_PROFIT - (9000.0 - 8200.0))
    result = reconcile(db, "2026-04", client=FakeQBOClient(report))

    assert result.overall_status == "discrepancies_found"
    rent_line = next(line for line in result.lines if line.account_code == "6010")
    assert rent_line.status == "mismatch"
    assert rent_line.app_amount == -8200.0
    assert rent_line.qbo_amount == -9000.0
    assert rent_line.difference == 800.0


def test_reconciliation_flags_account_missing_in_qbo(client):
    db = _setup(client)
    missing_one = {k: v for k, v in APRIL_LINES.items() if k != "6080"}  # drop Bank Fees entirely
    report = _build_report(missing_one, APRIL_NET_PROFIT + 35.0)
    result = reconcile(db, "2026-04", client=FakeQBOClient(report))

    bank_fees_line = next(line for line in result.lines if line.account_code == "6080")
    assert bank_fees_line.status == "app_only"
    assert bank_fees_line.qbo_amount == 0.0
    assert result.overall_status == "discrepancies_found"


def test_reconciliation_matches_by_name_when_qbo_id_not_in_mapping(client):
    db = _setup(client)
    lines = dict(APRIL_LINES)
    report = _build_report(lines, APRIL_NET_PROFIT)
    # Simulate QBO reporting an account_id we have no mapping for (e.g. accounts/sync
    # was never run for this one) - should still match by name.
    report["Rows"]["Row"][0]["Rows"]["Row"][0]["ColData"][0]["id"] = "some-unmapped-id"
    result = reconcile(db, "2026-04", client=FakeQBOClient(report))
    revenue_line = next(line for line in result.lines if line.account_code == "4000")
    assert revenue_line.status == "match"
