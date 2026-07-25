from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from pymongo.database import Database

from app.classification.coa import is_valid_account_code
from app.classification.service import apply_review
from app.deps import db_dep
from app.models.transaction import NormalizedTransaction, RawTransaction, TransactionType

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class ReviewRequest(BaseModel):
    transaction_type: TransactionType
    qbo_account: str | None = None
    counterparty: str | None = None
    apply_to_similar: bool = True


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


@router.post("/{transaction_id}/review", response_model=NormalizedTransaction)
def review_transaction(transaction_id: str, payload: ReviewRequest, db: Database = Depends(db_dep)):
    doc = db["normalized_transactions"].find_one({"id": transaction_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if doc["status"] != "ok":
        raise HTTPException(status_code=400, detail=f"Cannot classify a transaction with status '{doc['status']}'")
    if payload.qbo_account is not None and payload.transaction_type != "transfer" and not is_valid_account_code(payload.qbo_account):
        raise HTTPException(status_code=400, detail=f"'{payload.qbo_account}' is not a valid chart-of-accounts account number")

    updated = apply_review(
        db,
        doc,
        transaction_type=payload.transaction_type,
        qbo_account=payload.qbo_account,
        counterparty=payload.counterparty,
        apply_to_similar=payload.apply_to_similar,
    )
    updated.pop("_id", None)
    return NormalizedTransaction(**updated)
