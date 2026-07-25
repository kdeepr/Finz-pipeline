"""
Normalization: turns one raw row (a plain dict of source column -> string,
exactly as parsed) into a NormalizedTransaction, per column-mapping profile.

This is the only place dates, amounts, currency, bank accounts, and
descriptions get interpreted. Every parse failure is recorded as a flag rather
than raised as an exception - PDF 4.2 requires flagging unsafe records instead
of dropping them, so a single bad row must never abort the batch.
"""
import hashlib
import re
from datetime import datetime

from pymongo.database import Database

from app.ingestion.bank_accounts import resolve_bank_account
from app.models.column_mapping import ColumnMappingProfile
from app.models.transaction import NormalizedTransaction

# Common bank-statement date formats, tried in order when the mapping profile
# doesn't pin down an explicit one. US-centric (month before day) because the
# challenge dataset and the assumed bank are US-based; a non-US bank export
# should set an explicit date_format on its mapping profile instead of relying
# on this guesswork.
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%Y/%m/%d",
    "%d-%b-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
]

_CURRENCY_STRIP_RE = re.compile(r"[,$\s]")


def _get_mapped(row: dict[str, str], field_map: dict[str, str], canonical_field: str) -> str | None:
    source_col = field_map.get(canonical_field)
    if source_col is None:
        return None
    value = row.get(source_col)
    if value is None:
        return None
    value = value.strip()
    return value or None


def parse_date(value: str | None, date_format: str | None) -> str | None:
    if not value:
        return None
    if date_format:
        try:
            return datetime.strptime(value, date_format).date().isoformat()
        except ValueError:
            return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def parse_amount(value: str | None) -> float | None:
    if not value:
        return None
    cleaned = value.strip()
    negative = False
    if cleaned.startswith("(") and cleaned.endswith(")"):
        negative = True
        cleaned = cleaned[1:-1]
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    cleaned = _CURRENCY_STRIP_RE.sub("", cleaned)
    if not cleaned:
        return None
    try:
        amount = round(float(cleaned), 2)
    except ValueError:
        return None
    return -amount if negative else amount


def normalize_description(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip() or None


def compute_dedup_key(
    external_id: str | None,
    transaction_date: str | None,
    amount: float | None,
    bank_account: str | None,
    bank_account_raw: str | None,
    description_normalized: str | None,
) -> str:
    if external_id:
        return f"id:{external_id}"
    basis = "|".join(
        [
            transaction_date or "",
            f"{amount:.2f}" if amount is not None else "",
            (bank_account or bank_account_raw or "").lower(),
            (description_normalized or "").lower(),
        ]
    )
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"hash:{digest}"


def normalize_row(
    db: Database,
    row: dict[str, str],
    mapping: ColumnMappingProfile,
    bank_account_override: str | None = None,
    allowed_currencies: list[str] | None = None,
) -> NormalizedTransaction:
    allowed_currencies = allowed_currencies or ["USD"]
    field_map = mapping.field_map
    flags: list[str] = []

    external_id = _get_mapped(row, field_map, "external_id")

    raw_date = _get_mapped(row, field_map, "transaction_date")
    transaction_date = parse_date(raw_date, mapping.date_format)
    if raw_date and transaction_date is None:
        flags.append("unparseable_transaction_date")
    elif not raw_date:
        flags.append("missing_transaction_date")

    raw_posted = _get_mapped(row, field_map, "posted_date")
    posted_date = parse_date(raw_posted, mapping.date_format) if raw_posted else None

    raw_amount = _get_mapped(row, field_map, "amount")
    amount = parse_amount(raw_amount)
    if raw_amount and amount is None:
        flags.append("unparseable_amount")
    elif not raw_amount:
        flags.append("missing_amount")
    direction = None
    if amount is not None:
        direction = "credit" if amount >= 0 else "debit"

    currency = _get_mapped(row, field_map, "currency") or mapping.default_currency
    currency = currency.upper()
    if currency not in allowed_currencies:
        flags.append("unsupported_currency")

    bank_account_raw = bank_account_override or _get_mapped(row, field_map, "bank_account")
    bank_account = resolve_bank_account(db, bank_account_raw)
    if bank_account_raw and bank_account is None:
        flags.append("unrecognized_bank_account")
    elif not bank_account_raw:
        flags.append("missing_bank_account")

    description_raw = _get_mapped(row, field_map, "description")
    description_normalized = normalize_description(description_raw)
    if not description_normalized:
        flags.append("missing_description")

    dedup_key = compute_dedup_key(
        external_id, transaction_date, amount, bank_account, bank_account_raw, description_normalized
    )

    status = "needs_review" if flags else "ok"

    return NormalizedTransaction(
        batch_id="",  # filled in by the ingestion service
        raw_id="",  # filled in by the ingestion service
        external_id=external_id,
        transaction_date=transaction_date,
        posted_date=posted_date,
        amount=amount,
        currency=currency,
        direction=direction,
        bank_account_raw=bank_account_raw,
        bank_account=bank_account,
        description_raw=description_raw,
        description_normalized=description_normalized,
        dedup_key=dedup_key,
        status=status,
        flags=flags,
    )
