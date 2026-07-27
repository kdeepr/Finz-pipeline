import re

# Ordered longest-first so "CHECK DEPOSIT" doesn't get shadowed by "CHECK DEP".
_PREFIXES = [
    "ONLINE TRANSFER TO",
    "ONLINE TRANSFER FROM",
    "ACH REFUND TO",
    "ACH CREDIT",
    "MOBILE DEPOSIT",
    "CHECK DEPOSIT",
    "CHECK DEP",
    "ZELLE FROM",
    "WIRE FROM",
    "WIRE",
    "AUTO PAY",
    "OWNER DISTRIBUTION",
]
_PREFIX_RE = re.compile(r"^(?:" + "|".join(_PREFIXES) + r")\s+", re.IGNORECASE)

_SUFFIXES = [
    "EQUIPMENT INSTALL",
    "SERVICE PLAN",
    "MAINT PLAN",
    "OWNER CAPITAL",
    "TAX RESERVE TRANSFER",
    "JOB",
    "SERVICE",
    "REPAIR",
    "INSTALL",
    "PROJECT",
    "INV",
]
_SUFFIX_RE = re.compile(r"\s+(?:" + "|".join(_SUFFIXES) + r")\b.*$", re.IGNORECASE)


def extract_counterparty(description: str | None) -> str | None:
    if not description:
        return None
    text = _PREFIX_RE.sub("", description.strip())
    text = _SUFFIX_RE.sub("", text)
    text = text.strip()
    return text or None
