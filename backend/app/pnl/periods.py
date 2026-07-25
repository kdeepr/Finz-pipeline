"""
Period resolution for the P&L. Deliberately does not hardcode "April/May/June
2026" anywhere - the available monthly periods (and the bounds of "full") are
derived from whatever P&L-eligible transactions have actually been ingested
and classified, the same way a real accounting system's period list grows as
data comes in. This challenge's dataset happens to span Apr-Jun 2026, but the
same code works for any other date range.
"""
import calendar
from datetime import date

from pymongo.database import Database

PNL_ELIGIBLE_TYPES = ["revenue", "refund", "cogs", "operating_expense"]


def _eligible_query() -> dict:
    return {"status": "ok", "transaction_type": {"$in": PNL_ELIGIBLE_TYPES}, "transaction_date": {"$ne": None}}


def available_periods(db: Database) -> list[str]:
    months = sorted(
        {doc["transaction_date"][:7] for doc in db["normalized_transactions"].find(_eligible_query(), {"transaction_date": 1})}
    )
    return months


def period_bounds(db: Database, period: str) -> tuple[date, date]:
    if period == "full":
        months = available_periods(db)
        if not months:
            today = date.today()
            return today, today
        start = date.fromisoformat(months[0] + "-01")
        last_year, last_month = (int(x) for x in months[-1].split("-"))
        end = date(last_year, last_month, calendar.monthrange(last_year, last_month)[1])
        return start, end

    year, month = (int(x) for x in period.split("-"))
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start, end


def period_label(period: str, start: date, end: date) -> str:
    if period == "full":
        return f"{start.strftime('%b')} {start.day}, {start.year} - {end.strftime('%b')} {end.day}, {end.year}"
    return start.strftime("%B %Y")
