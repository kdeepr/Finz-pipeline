from pydantic import BaseModel


class ReconciliationLine(BaseModel):
    account_code: str | None
    account_name: str
    app_amount: float
    qbo_amount: float
    difference: float
    status: str  # "match" | "mismatch" | "app_only" | "qbo_only"
    explanation: str


class ReconciliationReport(BaseModel):
    period: str
    period_label: str
    lines: list[ReconciliationLine]
    app_net_profit: float
    qbo_net_profit: float
    net_profit_difference: float
    overall_status: str  # "reconciled" | "discrepancies_found"
    generated_at: str
