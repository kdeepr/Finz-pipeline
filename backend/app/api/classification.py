from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pymongo.database import Database

from app.classification import corrections
from app.classification.service import classify_pending
from app.deps import db_dep

router = APIRouter(prefix="/api/classification", tags=["classification"])


class RunRequest(BaseModel):
    batch_id: str | None = None


@router.post("/run")
def run_classification(payload: RunRequest = RunRequest(), db: Database = Depends(db_dep)):
    return classify_pending(db, batch_id=payload.batch_id)


@router.get("/rules")
def list_rules(db: Database = Depends(db_dep)):
    return corrections.list_rules(db)
