from pydantic import BaseModel


class PnLAccountLine(BaseModel):
    account_code: str
    account_name: str
    total: float
    transaction_count: int


class PnLSection(BaseModel):
    lines: list[PnLAccountLine]
    subtotal: float


class PnLStatement(BaseModel):
    period: str  # "YYYY-MM" or "full"
    period_label: str
    start_date: str
    end_date: str
    revenue: PnLSection
    cogs: PnLSection
    gross_profit: float
    operating_expenses: PnLSection
    net_profit: float
    excluded_unclassified_count: int
    generated_at: str
