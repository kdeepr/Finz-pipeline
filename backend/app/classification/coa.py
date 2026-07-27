import json
from functools import lru_cache
from pathlib import Path

# backend/app/classification/coa.py -> repo root is 3 parents up
_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "reference" / "qbo_chart_of_accounts.json"


@lru_cache
def load_chart_of_accounts(path: Path = _DEFAULT_PATH) -> list[dict]:
    with open(path) as f:
        return json.load(f)


@lru_cache
def accounts_by_code(path: Path = _DEFAULT_PATH) -> dict[str, dict]:
    return {a["Account No."]: a for a in load_chart_of_accounts(path)}


def account_name(code: str) -> str | None:
    acct = accounts_by_code().get(code)
    return acct["Account Name"] if acct else None


def is_valid_account_code(code: str) -> bool:
    return code in accounts_by_code()
