import pytest

from app.qbo.mapper import UnmappableTransactionError, build_qbo_payload, build_transfer_payload

FAKE_QBO_IDS = {
    "1000": "qbo-1000",  # Operating Checking
    "1010": "qbo-1010",  # Tax Reserve
    "1500": "qbo-1500",  # Tools & Equipment
    "3000": "qbo-3000",  # Owner's Equity
    "4000": "qbo-4000",  # Repair Service Revenue
    "4100": "qbo-4100",  # Customer Refunds
    "5010": "qbo-5010",  # Subcontractor Costs
    "6010": "qbo-6010",  # Rent Expense
}


def get_qbo_id(code: str) -> str:
    return FAKE_QBO_IDS[code]


def _txn(**overrides):
    base = {
        "id": "t1",
        "transaction_date": "2026-04-01",
        "amount": -100.0,
        "direction": "debit",
        "bank_account": "Operating Checking",
        "description_normalized": "SOME DESC",
        "counterparty": "Some Vendor",
        "transaction_type": "operating_expense",
        "qbo_account": "6010",
    }
    base.update(overrides)
    return base


def test_revenue_maps_to_deposit_against_income_account():
    txn = _txn(transaction_type="revenue", qbo_account="4000", direction="credit", amount=3425.0)
    payload = build_qbo_payload(txn, get_qbo_id)
    assert payload.entity_type == "deposit"
    assert payload.body["DepositToAccountRef"]["value"] == "qbo-1000"
    assert payload.body["Line"][0]["DepositLineDetail"]["AccountRef"]["value"] == "qbo-4000"
    assert payload.body["Line"][0]["Amount"] == 3425.0


def test_expense_maps_to_purchase_against_expense_account():
    txn = _txn(transaction_type="operating_expense", qbo_account="6010", direction="debit", amount=-8200.0)
    payload = build_qbo_payload(txn, get_qbo_id)
    assert payload.entity_type == "purchase"
    assert payload.body["AccountRef"]["value"] == "qbo-1000"
    assert payload.body["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "qbo-6010"
    assert payload.body["Line"][0]["Amount"] == 8200.0  # always positive magnitude


def test_refund_maps_to_purchase_against_customer_refunds_income_account():
    # A refund is money OUT (debit) but posts against an Income-type account
    # (4100) so it nets against revenue - Purchase supports any AccountRef
    # regardless of account type, which is exactly what we need here.
    txn = _txn(transaction_type="refund", qbo_account="4100", direction="debit", amount=-1250.0)
    payload = build_qbo_payload(txn, get_qbo_id)
    assert payload.entity_type == "purchase"
    assert payload.body["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "qbo-4100"


def test_fixed_asset_maps_to_purchase_against_fixed_asset_account():
    txn = _txn(transaction_type="fixed_asset", qbo_account="1500", direction="debit", amount=-6800.0)
    payload = build_qbo_payload(txn, get_qbo_id)
    assert payload.entity_type == "purchase"
    assert payload.body["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "qbo-1500"


def test_owner_contribution_maps_to_deposit_against_equity():
    txn = _txn(transaction_type="owner_activity", qbo_account="3000", direction="credit", amount=25000.0)
    payload = build_qbo_payload(txn, get_qbo_id)
    assert payload.entity_type == "deposit"
    assert payload.body["Line"][0]["DepositLineDetail"]["AccountRef"]["value"] == "qbo-3000"


def test_owner_distribution_maps_to_purchase_against_equity():
    txn = _txn(transaction_type="owner_activity", qbo_account="3000", direction="debit", amount=-5000.0)
    payload = build_qbo_payload(txn, get_qbo_id)
    assert payload.entity_type == "purchase"
    assert payload.body["Line"][0]["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] == "qbo-3000"


def test_transfer_is_rejected_by_build_qbo_payload():
    txn = _txn(transaction_type="transfer", qbo_account=None, direction="debit", amount=-5000.0, bank_account="Operating Checking")
    with pytest.raises(UnmappableTransactionError):
        build_qbo_payload(txn, get_qbo_id)


def test_build_transfer_payload_uses_native_transfer_entity():
    txn = _txn(transaction_type="transfer", direction="debit", amount=-5000.0)
    payload = build_transfer_payload(txn, from_bank_id="qbo-1000", to_bank_id="qbo-1010")
    assert payload.entity_type == "transfer"
    assert payload.body["FromAccountRef"]["value"] == "qbo-1000"
    assert payload.body["ToAccountRef"]["value"] == "qbo-1010"
    assert payload.body["Amount"] == 5000.0


def test_missing_qbo_account_raises_clear_error():
    txn = _txn(transaction_type="operating_expense", qbo_account=None)
    with pytest.raises(UnmappableTransactionError):
        build_qbo_payload(txn, get_qbo_id)
