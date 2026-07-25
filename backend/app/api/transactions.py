from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.deps import db_dep
from app.models.transaction import NormalizedTransaction, RawTransaction

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("", response_model=list[NormalizedTransaction])
def list_transactions(
    status: str | None = None,
    batch_id: str | None = None,
    bank_account: str | None = None,
    q: str | None = Query(None, description="Case-insensitive substring search over the description"),
    skip: int = 0,
    limit: int = 200,
    db: Database = Depends(db_dep),
):
    query: dict = {}
    if status:
        query["status"] = status
    if batch_id:
        query["batch_id"] = batch_id
    if bank_account:
        query["bank_account"] = bank_account
    if q:
        query["description_normalized"] = {"$regex": q, "$options": "i"}

    cursor = db["normalized_transactions"].find(query, {"_id": 0}).sort("transaction_date", 1).skip(skip).limit(limit)
    return [NormalizedTransaction(**doc) for doc in cursor]


@router.get("/{transaction_id}")
def get_transaction(transaction_id: str, db: Database = Depends(db_dep)):
    doc = db["normalized_transactions"].find_one({"id": transaction_id}, {"_id": 0})
    if doc is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    normalized = NormalizedTransaction(**doc)
    raw_doc = db["raw_transactions"].find_one({"id": normalized.raw_id}, {"_id": 0})
    duplicate_of = None
    if normalized.duplicate_of:
        dup_doc = db["normalized_transactions"].find_one({"id": normalized.duplicate_of}, {"_id": 0})
        duplicate_of = NormalizedTransaction(**dup_doc) if dup_doc else None
    return {
        "normalized": normalized,
        "raw": RawTransaction(**raw_doc) if raw_doc else None,
        "duplicate_of": duplicate_of,
    }
