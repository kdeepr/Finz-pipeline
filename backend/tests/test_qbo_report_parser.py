from app.reconciliation.qbo_report_parser import parse_profit_and_loss

SAMPLE_REPORT = {
    "Header": {"ReportName": "ProfitAndLoss", "StartPeriod": "2026-04-01", "EndPeriod": "2026-04-30"},
    "Rows": {
        "Row": [
            {
                "type": "Section",
                "group": "Income",
                "Rows": {
                    "Row": [
                        {"type": "Data", "ColData": [{"value": "Repair Service Revenue", "id": "80"}, {"value": "42775.00"}]},
                        {"type": "Data", "ColData": [{"value": "Installation Revenue", "id": "81"}, {"value": "53000.00"}]},
                        {"type": "Data", "ColData": [{"value": "Customer Refunds", "id": "83"}, {"value": "-1250.00"}]},
                    ]
                },
                "Summary": {"ColData": [{"value": "Total Income"}, {"value": "94525.00"}]},
            },
            {
                "type": "Section",
                "group": "COGS",
                "Rows": {
                    "Row": [
                        {"type": "Data", "ColData": [{"value": "5000 Materials & Supplies", "id": "90"}, {"value": "-15025.00"}]},
                    ]
                },
                "Summary": {"ColData": [{"value": "Total COGS"}, {"value": "-15025.00"}]},
            },
            {"type": "Section", "group": "GrossProfit", "Summary": {"ColData": [{"value": "Gross Profit"}, {"value": "79500.00"}]}},
            {
                "type": "Section",
                "group": "Expenses",
                "Rows": {
                    "Row": [
                        {"type": "Data", "ColData": [{"value": "Rent Expense", "id": "101"}, {"value": "-8200.00"}]},
                    ]
                },
                "Summary": {"ColData": [{"value": "Total Expenses"}, {"value": "-8200.00"}]},
            },
            {"type": "Section", "group": "NetOperatingIncome", "Summary": {"ColData": [{"value": "Net Operating Income"}, {"value": "71300.00"}]}},
            {"type": "Section", "group": "NetIncome", "Summary": {"ColData": [{"value": "Net Income"}, {"value": "71300.00"}]}},
        ]
    },
}


def test_parses_nested_data_rows_across_sections():
    result = parse_profit_and_loss(SAMPLE_REPORT)
    names = {a["account_name"]: a["amount"] for a in result["accounts"]}
    assert names["Repair Service Revenue"] == 42775.00
    assert names["Installation Revenue"] == 53000.00
    assert names["Customer Refunds"] == -1250.00
    assert names["Rent Expense"] == -8200.00


def test_strips_leading_account_number_prefix_when_present():
    result = parse_profit_and_loss(SAMPLE_REPORT)
    names = [a["account_name"] for a in result["accounts"]]
    assert "Materials & Supplies" in names
    assert "5000 Materials & Supplies" not in names


def test_captures_qbo_account_id_for_exact_matching():
    result = parse_profit_and_loss(SAMPLE_REPORT)
    by_name = {a["account_name"]: a["qbo_account_id"] for a in result["accounts"]}
    assert by_name["Repair Service Revenue"] == "80"


def test_captures_section_totals_including_net_income():
    result = parse_profit_and_loss(SAMPLE_REPORT)
    assert result["section_totals"]["Income"] == 94525.00
    assert result["section_totals"]["COGS"] == -15025.00
    assert result["section_totals"]["NetIncome"] == 71300.00


def test_empty_report_does_not_crash():
    result = parse_profit_and_loss({"Rows": {"Row": []}})
    assert result == {"accounts": [], "section_totals": {}}


def test_parent_account_with_subaccounts_reports_its_own_header_amount():
    """
    Spot-checked against a real sandbox report: a parent account with
    sub-accounts (e.g. "Utilities" over "Gas and Electric"/"Telephone") comes
    back as a Section whose OWN direct-posted total sits in "Header", not a
    Data row - a plain Data-row walk silently drops it entirely.
    """
    report = {
        "Rows": {
            "Row": [
                {
                    "type": "Section",
                    "group": "Expenses",
                    "Rows": {
                        "Row": [
                            {
                                "type": "Section",
                                "Header": {"ColData": [{"value": "Utilities", "id": "24"}, {"value": "3645.00"}]},
                                "Rows": {
                                    "Row": [
                                        {"type": "Data", "ColData": [{"value": "Gas and Electric", "id": "76"}, {"value": "114.09"}]},
                                        {"type": "Data", "ColData": [{"value": "Telephone", "id": "77"}, {"value": "130.86"}]},
                                    ]
                                },
                                "Summary": {"ColData": [{"value": "Total Utilities"}, {"value": "3889.95"}]},
                            },
                        ]
                    },
                    "Summary": {"ColData": [{"value": "Total Expenses"}, {"value": "3889.95"}]},
                },
            ]
        }
    }
    result = parse_profit_and_loss(report)
    by_name = {a["account_name"]: (a["amount"], a["qbo_account_id"]) for a in result["accounts"]}
    assert by_name["Utilities"] == (3645.00, "24")
    assert by_name["Gas and Electric"] == (114.09, "76")
    assert by_name["Telephone"] == (130.86, "77")
