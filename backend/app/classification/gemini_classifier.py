"""
Gemini-assisted classification - the fallback for whatever the deterministic
rule engine can't resolve (an unrecognized vendor, an unusual debit memo).
This is intentionally the *last* resort, not the primary classifier: rules are
free, instant, and traceable to a specific Company Setup sentence; an LLM call
is none of those things, so we only pay for it when the mechanical approach
comes up empty.

If GEMINI_API_KEY isn't configured, this module simply isn't invoked (see
classification/service.py) - the transaction stays "unclassified" for manual
review rather than blocking the pipeline.
"""
import json

from app.classification.coa import load_chart_of_accounts, is_valid_account_code
from app.classification.rules import ClassificationResult
from app.config import Settings

_PROMPT_TEMPLATE = """You are classifying one bank transaction for a cash-basis P&L for a home repair \
and installation services company. Choose the single best QBO account from this chart of accounts:

{accounts}

Accounting rules:
- Customer payments for completed repair/installation work are revenue.
- Monthly maintenance-plan receipts are revenue when received.
- Materials and subcontractor payments are Cost of Goods Sold.
- Payroll, rent, fuel, software, marketing, insurance, utilities, professional fees, bank fees, \
office costs, and repairs are operating expenses.
- Refunds reduce revenue (negative revenue), not an expense.
- Owner contributions/distributions affect equity, not the P&L.
- Transfers between the company's own bank accounts are not revenue or expense.
- A commercial tool/equipment purchase (not a customer job) is a fixed asset.

Transaction:
  description: {description}
  amount: {amount}
  direction: {direction} (credit = money in, debit = money out)
  bank_account: {bank_account}

Respond with ONLY a JSON object, no markdown fences, in this exact shape:
{{"transaction_type": "revenue|refund|cogs|operating_expense|transfer|owner_activity|fixed_asset", \
"qbo_account_code": "<Account No. from the chart above, or null for transfer>", \
"counterparty": "<clean counterparty name or null>", \
"confidence": <0.0-1.0>, \
"explanation": "<one sentence citing which rule above applies>"}}
"""


def _build_prompt(description: str, amount: float, direction: str, bank_account: str) -> str:
    accounts = "\n".join(
        f"- {a['Account No.']} {a['Account Name']} ({a['QBO Account Type']}): {a['Purpose']}"
        for a in load_chart_of_accounts()
    )
    return _PROMPT_TEMPLATE.format(
        accounts=accounts, description=description, amount=amount, direction=direction, bank_account=bank_account
    )


def _call_gemini(prompt: str, settings: Settings) -> str:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    model = genai.GenerativeModel(settings.gemini_model)
    response = model.generate_content(prompt)
    return response.text


def classify_with_gemini(
    settings: Settings,
    description: str,
    amount: float,
    direction: str,
    bank_account: str,
    call_fn=_call_gemini,
) -> ClassificationResult | None:
    if not settings.gemini_api_key:
        return None

    prompt = _build_prompt(description, amount, direction, bank_account)
    try:
        raw = call_fn(prompt, settings)
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
    except Exception as exc:  # noqa: BLE001 - any Gemini/parsing failure just falls through to manual review
        return ClassificationResult(
            transaction_type="uncategorized",
            qbo_account=None,
            counterparty=None,
            confidence=0.0,
            explanation=f"Gemini classification failed ({exc.__class__.__name__}); needs manual review.",
            source="gemini_error",
        )

    qbo_account = parsed.get("qbo_account_code")
    if qbo_account is not None and not is_valid_account_code(qbo_account):
        qbo_account = None

    return ClassificationResult(
        transaction_type=parsed.get("transaction_type", "uncategorized"),
        qbo_account=qbo_account,
        counterparty=parsed.get("counterparty"),
        confidence=float(parsed.get("confidence", 0.5)),
        explanation=parsed.get("explanation", "Classified by Gemini."),
        source="gemini",
    )
