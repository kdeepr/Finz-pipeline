from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.deps import db_dep
from app.models.reconciliation import ReconciliationReport
from app.qbo.client import QBONotConnectedError
from app.qbo.connection_store import get_connection
from app.reconciliation.service import reconcile

router = APIRouter(prefix="/api/reconciliation", tags=["reconciliation"])


@router.get("/{period}", response_model=ReconciliationReport)
def get_reconciliation(period: str, db: Database = Depends(db_dep)):
    if get_connection(db) is None:
        raise HTTPException(status_code=400, detail="Not connected to QuickBooks Online. Visit GET /api/qbo/connect first.")
    try:
        return reconcile(db, period)
    except QBONotConnectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
