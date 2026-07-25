from fastapi import APIRouter, Depends, HTTPException
from pymongo.database import Database

from app.deps import db_dep
from app.models.pnl import PnLStatement
from app.models.transaction import NormalizedTransaction
from app.pnl.periods import available_periods
from app.pnl.service import compute_pnl, transactions_for_line

router = APIRouter(prefix="/api/pnl", tags=["pnl"])


@router.get("/periods")
def list_periods(db: Database = Depends(db_dep)):
    periods = available_periods(db)
    return {"months": periods, "full": "full" if periods else None}


@router.get("/{period}", response_model=PnLStatement)
def get_pnl(period: str, db: Database = Depends(db_dep)):
    if period != "full":
        try:
            year, month = (int(x) for x in period.split("-"))
            assert 1 <= month <= 12
        except (ValueError, AssertionError):
            raise HTTPException(status_code=400, detail="period must be 'full' or 'YYYY-MM'")
    return compute_pnl(db, period)


@router.get("/{period}/accounts/{account_code}/transactions", response_model=list[NormalizedTransaction])
def get_pnl_line_transactions(period: str, account_code: str, db: Database = Depends(db_dep)):
    return transactions_for_line(db, period, account_code)
