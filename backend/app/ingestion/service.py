"""
Ingestion orchestration: parse -> for each row, preserve raw + normalize +
dedup-check -> persist. This is the single entry point the API layer calls;
everything else in app/ingestion is a building block this wires together.
"""
from pymongo.database import Database

from app.ingestion.duplicates import find_existing_by_dedup_key
from app.ingestion.normalizer import normalize_row
from app.ingestion.parser import parse_file
from app.models.column_mapping import ColumnMappingProfile
from app.models.transaction import NormalizedTransaction, RawTransaction
from app.models.upload_batch import UploadBatch

RAW_COLLECTION = "raw_transactions"
NORMALIZED_COLLECTION = "normalized_transactions"
BATCH_COLLECTION = "upload_batches"


class MappingMismatchError(ValueError):
    """Raised when a mapping profile references source columns the file doesn't have."""


def _validate_mapping_against_headers(mapping: ColumnMappingProfile, headers: list[str]) -> None:
    header_set = set(headers)
    missing = [
        f"{canonical} -> '{source_col}'"
        for canonical, source_col in mapping.field_map.items()
        if source_col not in header_set
    ]
    if missing:
        raise MappingMismatchError(
            "Mapping profile '"
            + mapping.name
            + "' references columns not present in the uploaded file: "
            + ", ".join(missing)
            + f". File columns are: {headers}"
        )


def ingest_file(
    db: Database,
    filename: str,
    content: bytes,
    mapping: ColumnMappingProfile,
    bank_account_override: str | None = None,
    allowed_currencies: list[str] | None = None,
) -> UploadBatch:
    headers, rows = parse_file(filename, content)
    _validate_mapping_against_headers(mapping, headers)

    batch = UploadBatch(
        filename=filename,
        mapping_profile_id=mapping.id,
        mapping_profile_name=mapping.name,
        row_count=len(rows),
    )
    db[BATCH_COLLECTION].insert_one(batch.model_dump())

    ok = duplicate = needs_review = 0

    for idx, row in enumerate(rows):
        raw = RawTransaction(
            batch_id=batch.id,
            source_filename=filename,
            row_index=idx,
            fields=row,
        )
        db[RAW_COLLECTION].insert_one(raw.model_dump())

        normalized = normalize_row(
            db, row, mapping, bank_account_override=bank_account_override, allowed_currencies=allowed_currencies
        )
        normalized.batch_id = batch.id
        normalized.raw_id = raw.id

        if normalized.status == "ok":
            existing = find_existing_by_dedup_key(db, normalized.dedup_key)
            if existing:
                normalized.status = "duplicate"
                normalized.duplicate_of = existing["id"]

        db[NORMALIZED_COLLECTION].insert_one(normalized.model_dump())

        if normalized.status == "ok":
            ok += 1
        elif normalized.status == "duplicate":
            duplicate += 1
        else:
            needs_review += 1

    db[BATCH_COLLECTION].update_one(
        {"id": batch.id},
        {"$set": {"ok_count": ok, "duplicate_count": duplicate, "needs_review_count": needs_review}},
    )
    batch.ok_count, batch.duplicate_count, batch.needs_review_count = ok, duplicate, needs_review
    return batch


def preview_file(filename: str, content: bytes, sample_size: int = 5) -> dict:
    headers, rows = parse_file(filename, content)
    return {"filename": filename, "headers": headers, "sample_rows": rows[:sample_size], "row_count": len(rows)}
