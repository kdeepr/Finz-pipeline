"""
Maps one classified NormalizedTransaction to a QuickBooks Online entity +
payload. This is the accounting/integration decision PDF 4.5 asks us to
explain, so the reasoning lives here as documentation, not just in the README:

- Revenue, refunds, COGS, operating expenses, fixed-asset purchases, and
  owner activity are all direct bank-to-account postings with no invoice, no
  bill, and no Product/Service item behind them - Company Setup explicitly
  puts AR and AP out of scope, and QuickBooks' SalesReceipt/Invoice line
  items require an ItemRef (a Product/Service), not a bare AccountRef, so
  using them would force us to invent an item catalog nothing in the
  dataset calls for. Deposit and Purchase, by contrast, both support posting
  a line directly against any account via AccountRef - no item required -
  which is exactly the shape of "money appeared in/left the bank account."
    - Money IN (credit direction)  -> Deposit, line against the classified account.
    - Money OUT (debit direction)  -> Purchase, line against the classified account.
  A refund is money OUT (a debit in the bank feed) posted to the Customer
  Refunds income account (4100) - Purchase against an Income-type account is
  valid in QBO and is what makes it net against revenue as Company Setup
  requires ("refunds reduce revenue"), without needing AR/Credit Memos.
- Transfers between the company's own two bank accounts use QuickBooks'
  native Transfer entity (FromAccountRef/ToAccountRef/Amount) instead of a
  Deposit+Purchase pair, because a Transfer is a single object that updates
  both bank registers atomically and is exactly what it's designed for -
  posting it as two separate cash transactions would double-count the money
  movement on the balance sheet. Only the "money out" leg of each transfer
  pair gets an API call; the paired "money in" leg is marked synced against
  the same QBO Transfer Id rather than posted again (see qbo/sync_service.py).

Every function here is pure (no HTTP calls) so the mapping logic itself is
fully unit-testable without a live QBO connection.
"""
from dataclasses import dataclass
from typing import Callable

BANK_ACCOUNT_NO = {"Operating Checking": "1000", "Tax Reserve": "1010"}

GetQboId = Callable[[str], str]


class UnmappableTransactionError(ValueError):
    pass


@dataclass
class QboPayload:
    entity_type: str  # "deposit" | "purchase" | "transfer"
    body: dict


def _bank_account_qbo_id(bank_account: str, get_qbo_id: GetQboId) -> str:
    account_no = BANK_ACCOUNT_NO.get(bank_account)
    if account_no is None:
        raise UnmappableTransactionError(f"Unknown bank account '{bank_account}'")
    return get_qbo_id(account_no)


def _deposit(txn: dict, target_account_id: str, bank_account_id: str) -> QboPayload:
    return QboPayload(
        entity_type="deposit",
        body={
            "TxnDate": txn["transaction_date"],
            "DepositToAccountRef": {"value": bank_account_id},
            "Line": [
                {
                    "Amount": abs(txn["amount"]),
                    "DetailType": "DepositLineDetail",
                    "DepositLineDetail": {"AccountRef": {"value": target_account_id}},
                    "Description": txn.get("description_normalized"),
                }
            ],
            "PrivateNote": f"Finz sync | txn_id={txn['id']} | {txn.get('counterparty') or ''}",
        },
    )


def _purchase(txn: dict, target_account_id: str, bank_account_id: str) -> QboPayload:
    return QboPayload(
        entity_type="purchase",
        body={
            "TxnDate": txn["transaction_date"],
            "AccountRef": {"value": bank_account_id},
            "PaymentType": "Cash",
            "Line": [
                {
                    "Amount": abs(txn["amount"]),
                    "DetailType": "AccountBasedExpenseLineDetail",
                    "AccountBasedExpenseLineDetail": {"AccountRef": {"value": target_account_id}},
                    "Description": txn.get("description_normalized"),
                }
            ],
            "PrivateNote": f"Finz sync | txn_id={txn['id']} | {txn.get('counterparty') or ''}",
        },
    )


def build_transfer_payload(txn: dict, from_bank_id: str, to_bank_id: str) -> QboPayload:
    return QboPayload(
        entity_type="transfer",
        body={
            "TxnDate": txn["transaction_date"],
            "FromAccountRef": {"value": from_bank_id},
            "ToAccountRef": {"value": to_bank_id},
            "Amount": abs(txn["amount"]),
            "PrivateNote": f"Finz sync | txn_id={txn['id']}",
        },
    )


def build_qbo_payload(txn: dict, get_qbo_id: GetQboId) -> QboPayload:
    ttype = txn.get("transaction_type")
    bank_account_id = _bank_account_qbo_id(txn["bank_account"], get_qbo_id)

    if ttype == "transfer":
        raise UnmappableTransactionError(
            "Transfers are paired and mapped via build_transfer_payload() in sync_service, not build_qbo_payload()."
        )

    if ttype not in {"revenue", "refund", "cogs", "operating_expense", "fixed_asset", "owner_activity"}:
        raise UnmappableTransactionError(f"Transaction type '{ttype}' has no QBO mapping.")

    if not txn.get("qbo_account"):
        raise UnmappableTransactionError(f"Transaction {txn.get('id')} has no qbo_account set.")

    target_account_id = get_qbo_id(txn["qbo_account"])

    if txn["direction"] == "credit":
        return _deposit(txn, target_account_id, bank_account_id)
    return _purchase(txn, target_account_id, bank_account_id)
