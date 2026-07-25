"""
Generalizes a transaction description into a stable "pattern signature" by
blanking out the parts that vary between otherwise-identical transactions:
job numbers, invoice numbers, dates, and month names. This is what lets a
single approved correction apply to every future transaction with the same
shape - e.g. "ACH PARKSIDE COMMERCIAL MGMT RENT APR" and "... RENT MAY"
collapse to the same signature, so correcting one rent payment teaches the
system the whole recurring pattern (PDF 4.3: "Store approved corrections so
repeated transaction patterns can be classified consistently").
"""
import re

_DIGIT_RE = re.compile(r"\d+")
_MONTH_RE = re.compile(r"\b(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\b", re.IGNORECASE)


def compute_signature(description: str | None, direction: str | None) -> str:
    text = (description or "").upper().strip()
    text = _DIGIT_RE.sub("#", text)
    text = _MONTH_RE.sub("{MONTH}", text)
    text = re.sub(r"\s+", " ", text).strip()
    return f"{direction or 'unknown'}|{text}"
