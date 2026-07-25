"""
Two collections back every transaction, by design (PDF 4.2: "Preserve the raw
source record and create a normalized transaction record"):

- RawTransaction: the row exactly as it appeared in the uploaded file. Untouched.
  Column names and values are whatever the source file had - we never coerce
  types or rewrite them. This is the audit trail back to "untrusted" input.
- NormalizedTransaction: the canonical, typed record derived from the raw row
  via a column-mapping profile. Everything downstream (classification, P&L,
  QBO sync) reads from here, never from the raw row.

Classification fields (transaction_type, counterparty, qbo_account, ...) live on
the same normalized record rather than a separate collection, because a
transaction has exactly one current classification at a time and the review UI
needs to show normalization + classification together. Approved corrections are
kept in a separate ClassificationRule collection (see classification/ module)
so the *pattern* is reusable, while the *outcome* for this specific transaction
stays on the transaction itself.
"""
from typing import Literal

from pydantic import BaseModel, Field

from app.models.common import new_id, utcnow

TransactionStatus = Literal["ok", "duplicate", "needs_review"]
Direction = Literal["credit", "debit"]

ClassificationStatus = Literal["unclassified", "auto", "reviewed", "corrected"]
TransactionType = Literal[
    "revenue",
    "refund",
    "cogs",
    "operating_expense",
    "transfer",
    "owner_activity",
    "fixed_asset",
    "uncategorized",
]


class RawTransaction(BaseModel):
    id: str = Field(default_factory=new_id)
    batch_id: str
    source_filename: str
    row_index: int  # 0-based position within the uploaded file, for traceability
    # Original column name -> original string value, exactly as parsed from the
    # file. No type coercion happens here - that is the normalizer's job.
    fields: dict[str, str | None]
    ingested_at: str = Field(default_factory=lambda: utcnow().isoformat())


class NormalizedTransaction(BaseModel):
    id: str = Field(default_factory=new_id)
    batch_id: str
    raw_id: str

    external_id: str | None = None
    transaction_date: str | None = None  # ISO 8601 date (YYYY-MM-DD)
    posted_date: str | None = None
    amount: float | None = None  # signed: positive = received, negative = paid
    currency: str | None = None
    direction: Direction | None = None

    bank_account_raw: str | None = None
    bank_account: str | None = None  # canonical account name, or None if unrecognized

    description_raw: str | None = None
    description_normalized: str | None = None

    dedup_key: str = ""
    status: TransactionStatus = "ok"
    duplicate_of: str | None = None
    flags: list[str] = Field(default_factory=list)

    # --- Classification (populated starting in 4.3) ---
    transaction_type: TransactionType | None = None
    counterparty: str | None = None
    qbo_account: str | None = None
    classification_confidence: float | None = None
    classification_explanation: str | None = None
    classification_status: ClassificationStatus = "unclassified"
    classification_source: str | None = None  # "rule" | "gemini" | "user"

    # --- QBO sync (populated starting in 4.5) ---
    qbo_txn_id: str | None = None
    qbo_sync_status: str | None = None  # "pending" | "synced" | "failed"
    qbo_sync_error: str | None = None
    qbo_synced_at: str | None = None

    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: utcnow().isoformat())

    def is_pnl_eligible(self) -> bool:
        """Transfers, owner activity, duplicates, and fixed assets never hit the P&L (PDF 4.4)."""
        if self.status != "ok":
            return False
        return self.transaction_type in {"revenue", "refund", "cogs", "operating_expense"}
