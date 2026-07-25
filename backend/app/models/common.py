"""Shared helpers for Mongo-backed Pydantic models."""
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    """We use string UUIDs (not ObjectId) as primary keys.

    Every downstream system that references a transaction id - the classification
    review UI, the QBO sync record, the reconciliation report - needs a stable,
    JSON-friendly, serializable key. UUID strings avoid ObjectId (de)serialization
    edge cases in the API layer and read the same in Mongo, in QBO's private notes,
    and in the frontend.
    """
    import uuid

    return str(uuid.uuid4())
