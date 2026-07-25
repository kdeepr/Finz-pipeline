"""
Column mapping profiles are what let the upload flow support "other common bank
CSV or Excel exports" (PDF 4.2) without hardcoding a single column order.

A profile just says, in the source file's own header names, which column holds
each canonical field. The parser never assumes a fixed column order or fixed
header text - it looks up whatever column name the profile points at.
"""
from pydantic import BaseModel, Field

from app.models.common import new_id, utcnow

# The canonical fields every mapping profile must (or may) supply.
REQUIRED_CANONICAL_FIELDS = ["transaction_date", "amount", "description", "bank_account"]
OPTIONAL_CANONICAL_FIELDS = ["external_id", "posted_date", "currency"]
ALL_CANONICAL_FIELDS = REQUIRED_CANONICAL_FIELDS + OPTIONAL_CANONICAL_FIELDS


class ColumnMappingProfile(BaseModel):
    id: str = Field(default_factory=new_id)
    name: str
    description: str = ""
    # canonical_field -> source column header, e.g. {"amount": "Amount (USD)"}
    field_map: dict[str, str]
    # Explicit strptime format if the bank's dates aren't unambiguously parseable
    # (e.g. "31/01/2026" needs "%d/%m/%Y" so it isn't misread as month 31).
    date_format: str | None = None
    # Some banks export debits as positive numbers with a separate type column,
    # or wrap negatives in parentheses. "signed" (default) means the amount
    # column already carries the correct sign per the Company Setup convention
    # (positive = received, negative = paid).
    amount_convention: str = "signed"
    default_currency: str = "USD"
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: utcnow().isoformat())

    def missing_required_fields(self) -> list[str]:
        return [f for f in REQUIRED_CANONICAL_FIELDS if f not in self.field_map]


class ColumnMappingCreate(BaseModel):
    name: str
    description: str = ""
    field_map: dict[str, str]
    date_format: str | None = None
    amount_convention: str = "signed"
    default_currency: str = "USD"
