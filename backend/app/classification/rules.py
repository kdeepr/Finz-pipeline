from dataclasses import dataclass

from pymongo.database import Database

from app.classification.counterparty import extract_counterparty
from app.classification.vendor_directory import lookup_vendor


@dataclass
class ClassificationResult:
    transaction_type: str
    qbo_account: str | None
    counterparty: str | None
    confidence: float
    explanation: str
    source: str  # "rule"


def classify_by_rules(
    db: Database,
    description: str | None,
    direction: str | None,
    bank_account: str | None,
) -> ClassificationResult | None:
    if not description:
        return None
    desc = description.upper()

    if "TAX RESERVE TRANSFER" in desc:
        other_account = "Tax Reserve" if bank_account == "Operating Checking" else "Operating Checking"
        return ClassificationResult(
            transaction_type="transfer",
            qbo_account=None,
            counterparty=other_account,
            confidence=1.0,
            explanation=(
                "Transfer between the company's own bank accounts (Operating Checking <-> Tax "
                "Reserve). Company Setup rules exclude transfers from revenue/expense - excluded "
                "from the P&L and posted in QBO as a bank transfer, not an income/expense account."
            ),
            source="rule",
        )

    if "OWNER CAPITAL" in desc or "OWNER DISTRIBUTION" in desc:
        return ClassificationResult(
            transaction_type="owner_activity",
            qbo_account="3000",
            counterparty=extract_counterparty(description),
            confidence=1.0,
            explanation=(
                "Owner contribution or distribution. Company Setup rules: owner activity affects "
                "equity, not the P&L."
            ),
            source="rule",
        )

    if desc.startswith("ACH REFUND TO"):
        return ClassificationResult(
            transaction_type="refund",
            qbo_account="4100",
            counterparty=extract_counterparty(description),
            confidence=1.0,
            explanation=(
                "Customer refund. Company Setup rules: refunds reduce revenue and post as negative "
                "revenue, not an expense."
            ),
            source="rule",
        )

    vendor = lookup_vendor(db, desc)
    if vendor:
        return ClassificationResult(
            transaction_type=vendor["transaction_type"],
            qbo_account=vendor["qbo_account_code"],
            counterparty=vendor["canonical_name"],
            confidence=1.0,
            explanation=f"Matched known vendor '{vendor['canonical_name']}' in the vendor directory.",
            source="rule",
        )

    if direction == "credit":
        counterparty = extract_counterparty(description)
        if "MAINT PLAN" in desc or "SERVICE PLAN" in desc:
            return ClassificationResult(
                transaction_type="revenue",
                qbo_account="4020",
                counterparty=counterparty,
                confidence=1.0,
                explanation=(
                    "Recurring maintenance-plan receipt. Company Setup rules: maintenance-plan "
                    "receipts are revenue when received."
                ),
                source="rule",
            )
        if "EQUIPMENT INSTALL" in desc or "INSTALL" in desc or "PROJECT" in desc:
            return ClassificationResult(
                transaction_type="revenue",
                qbo_account="4010",
                counterparty=counterparty,
                confidence=1.0,
                explanation="Installation project receipt (customer payment for an install job).",
                source="rule",
            )
        return ClassificationResult(
            transaction_type="revenue",
            qbo_account="4000",
            counterparty=counterparty,
            confidence=1.0,
            explanation="Customer payment for a completed repair/maintenance job.",
            source="rule",
        )

    return None
