"""Repository for column-mapping profiles (create/list/lookup)."""
from pymongo.database import Database

from app.models.column_mapping import ColumnMappingCreate, ColumnMappingProfile

COLLECTION = "column_mapping_profiles"

# Matches the header of the sample exports in data/sample_bank_exports/, i.e.
# the bank's own CSV format for this challenge. Any other bank's export just
# needs its own profile created via POST /api/column-mappings - nothing in the
# ingestion code changes.
DEFAULT_PROFILE = ColumnMappingCreate(
    name="brightfix_bank_csv_v1",
    description="Default mapping for the BrightFix sample bank exports (Operating Checking / Tax Reserve CSVs).",
    field_map={
        "external_id": "Bank Transaction ID",
        "transaction_date": "Transaction Date",
        "posted_date": "Posted Date",
        "description": "Description",
        "amount": "Amount (USD)",
        "currency": "Currency",
        "bank_account": "Bank Account",
    },
    date_format="%Y-%m-%d",
    default_currency="USD",
)


def seed_default_profile(db: Database) -> None:
    if db[COLLECTION].count_documents({"name": DEFAULT_PROFILE.name}) > 0:
        return
    create_profile(db, DEFAULT_PROFILE)


def create_profile(db: Database, payload: ColumnMappingCreate) -> ColumnMappingProfile:
    profile = ColumnMappingProfile(**payload.model_dump())
    db[COLLECTION].insert_one(profile.model_dump())
    return profile


def list_profiles(db: Database) -> list[ColumnMappingProfile]:
    return [ColumnMappingProfile(**doc) for doc in db[COLLECTION].find({}, {"_id": 0})]


def get_profile(db: Database, profile_id: str) -> ColumnMappingProfile | None:
    doc = db[COLLECTION].find_one({"id": profile_id}, {"_id": 0})
    if doc:
        return ColumnMappingProfile(**doc)
    # allow lookup by name too, for convenience
    doc = db[COLLECTION].find_one({"name": profile_id}, {"_id": 0})
    return ColumnMappingProfile(**doc) if doc else None
