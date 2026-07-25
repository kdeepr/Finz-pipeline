from fastapi import APIRouter

from app.classification.coa import load_chart_of_accounts

router = APIRouter(prefix="/api/chart-of-accounts", tags=["chart-of-accounts"])


@router.get("")
def get_chart_of_accounts():
    return load_chart_of_accounts()
