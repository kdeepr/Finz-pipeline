"""
Cross-checks the generated P&L against the dataset's known transactions.

test_net_profit_matches_expected_totals uses expected monthly net-profit
figures computed independently (summing every transaction's signed amount
except transfers/owner-activity/fixed-asset purchases directly off the
dataset, with no reference to this app's classification code) - so this test
doesn't just check "the code agrees with itself," it checks the code against
the source numbers.
"""
import io
from pathlib import Path

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

# Computed independently straight from the raw dataset (see conversation/
# analysis script): sum of every unique transaction's signed amount, excluding
# only transfers, owner capital/distribution, and the one fixed-asset
# purchase - i.e. exactly what PDF 4.4 says to exclude from the P&L.
EXPECTED_NET_PROFIT = {
    "2026-04": 21990.0,
    "2026-05": 28285.0,
    "2026-06": 17905.0,
}
EXPECTED_FULL_NET_PROFIT = 68180.0


def _ingest_and_classify(client):
    profile_id = client.get("/api/column-mappings").json()[0]["id"]
    for filename in ALL_SOURCE_FILES:
        content = (DATA_DIR / filename).read_bytes()
        files = {"file": (filename, io.BytesIO(content), "text/csv")}
        resp = client.post("/api/uploads", files=files, data={"mapping_profile_id": profile_id})
        assert resp.status_code == 200
    run = client.post("/api/classification/run").json()
    assert run["classified"] == 195


def test_available_periods_derived_from_data(client):
    _ingest_and_classify(client)
    periods = client.get("/api/pnl/periods").json()
    assert periods["months"] == ["2026-04", "2026-05", "2026-06"]


def test_net_profit_matches_expected_totals(client):
    _ingest_and_classify(client)
    for period, expected in EXPECTED_NET_PROFIT.items():
        pnl = client.get(f"/api/pnl/{period}").json()
        assert pnl["net_profit"] == expected, f"{period}: {pnl['net_profit']} != {expected}"
        assert pnl["excluded_unclassified_count"] == 0

    full = client.get("/api/pnl/full").json()
    assert full["net_profit"] == EXPECTED_FULL_NET_PROFIT
    assert full["start_date"] == "2026-04-01"
    assert full["end_date"] == "2026-06-30"


def test_full_period_equals_sum_of_months(client):
    _ingest_and_classify(client)
    full = client.get("/api/pnl/full").json()
    monthly_sum = sum(client.get(f"/api/pnl/{p}").json()["net_profit"] for p in ["2026-04", "2026-05", "2026-06"])
    assert round(full["net_profit"], 2) == round(monthly_sum, 2)


def test_gross_profit_and_net_profit_arithmetic(client):
    _ingest_and_classify(client)
    pnl = client.get("/api/pnl/2026-04").json()
    assert round(pnl["revenue"]["subtotal"] + pnl["cogs"]["subtotal"], 2) == pnl["gross_profit"]
    assert round(pnl["gross_profit"] + pnl["operating_expenses"]["subtotal"], 2) == pnl["net_profit"]


def test_refunds_appear_as_negative_line_within_revenue_section(client):
    _ingest_and_classify(client)
    pnl = client.get("/api/pnl/2026-04").json()
    refund_line = next(line for line in pnl["revenue"]["lines"] if line["account_code"] == "4100")
    assert refund_line["total"] == -1250.0
    assert refund_line["account_name"] == "Customer Refunds"


def test_transfers_owner_activity_and_fixed_asset_never_appear_in_pnl(client):
    _ingest_and_classify(client)
    pnl = client.get("/api/pnl/full").json()
    all_codes = {line["account_code"] for section in (pnl["revenue"], pnl["cogs"], pnl["operating_expenses"]) for line in section["lines"]}
    assert "3000" not in all_codes  # Owner's Equity
    assert "1500" not in all_codes  # Tools & Equipment (fixed asset)
    assert "1000" not in all_codes and "1010" not in all_codes  # bank accounts themselves


def test_drill_down_returns_underlying_transactions(client):
    _ingest_and_classify(client)
    pnl = client.get("/api/pnl/2026-04").json()
    rent_line = next(line for line in pnl["operating_expenses"]["lines"] if line["account_code"] == "6010")
    assert rent_line["total"] == -8200.0
    assert rent_line["transaction_count"] == 1

    txns = client.get("/api/pnl/2026-04/accounts/6010/transactions").json()
    assert len(txns) == 1
    assert txns[0]["amount"] == -8200.0
    assert "PARKSIDE" in txns[0]["description_normalized"]


def test_unclassified_transactions_are_excluded_but_counted(client):
    profile_id = client.get("/api/column-mappings").json()[0]["id"]
    csv_content = (
        "Bank Transaction ID,Transaction Date,Posted Date,Description,Amount (USD),Currency,Bank Account\n"
        "BF-MYSTERY-0001,2026-04-15,2026-04-15,SOME UNKNOWN VENDOR XYZ,-500.00,USD,Operating Checking\n"
    )
    files = {"file": ("mystery.csv", io.BytesIO(csv_content.encode()), "text/csv")}
    client.post("/api/uploads", files=files, data={"mapping_profile_id": profile_id})
    client.post("/api/classification/run")  # no rule/vendor match, no Gemini key configured -> stays unclassified

    pnl = client.get("/api/pnl/2026-04").json()
    assert pnl["excluded_unclassified_count"] == 1
    assert pnl["net_profit"] == 0.0  # the mystery transaction must not silently affect the total
