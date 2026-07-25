"""
Tests the Gemini fallback's parsing/validation logic with a stubbed call_fn -
no live network call, no API key required. This is the one part of the
pipeline that can't be exercised end-to-end without a real GEMINI_API_KEY, so
what we verify here is that the plumbing around a Gemini response (JSON
parsing, markdown-fence stripping, invalid-account-code rejection, and
error handling) behaves correctly regardless of what the model actually says.
"""
import json

from app.classification.gemini_classifier import classify_with_gemini
from app.config import Settings


def _settings_with_key():
    return Settings(gemini_api_key="test-key", mongodb_uri="mongomock://", testing=True)


def test_classify_with_gemini_returns_none_without_api_key():
    settings = Settings(gemini_api_key=None, testing=True)
    result = classify_with_gemini(settings, "SOME VENDOR", -100.0, "debit", "Operating Checking")
    assert result is None


def test_classify_with_gemini_parses_clean_json():
    def fake_call(prompt, settings):
        return json.dumps(
            {
                "transaction_type": "operating_expense",
                "qbo_account_code": "6090",
                "counterparty": "Some Office Store",
                "confidence": 0.82,
                "explanation": "Office supplies purchase.",
            }
        )

    result = classify_with_gemini(
        _settings_with_key(), "SOME OFFICE STORE #123", -50.0, "debit", "Operating Checking", call_fn=fake_call
    )
    assert result.transaction_type == "operating_expense"
    assert result.qbo_account == "6090"
    assert result.confidence == 0.82
    assert result.source == "gemini"


def test_classify_with_gemini_strips_markdown_fences():
    def fake_call(prompt, settings):
        return "```json\n" + json.dumps({"transaction_type": "cogs", "qbo_account_code": "5000", "confidence": 0.7, "explanation": "x"}) + "\n```"

    result = classify_with_gemini(_settings_with_key(), "DESC", -10.0, "debit", "Operating Checking", call_fn=fake_call)
    assert result.qbo_account == "5000"


def test_classify_with_gemini_rejects_invalid_account_code():
    def fake_call(prompt, settings):
        return json.dumps({"transaction_type": "operating_expense", "qbo_account_code": "9999", "confidence": 0.6, "explanation": "x"})

    result = classify_with_gemini(_settings_with_key(), "DESC", -10.0, "debit", "Operating Checking", call_fn=fake_call)
    assert result.qbo_account is None  # invalid code against the real chart of accounts is dropped, not trusted


def test_classify_with_gemini_handles_malformed_response():
    def fake_call(prompt, settings):
        return "not valid json at all"

    result = classify_with_gemini(_settings_with_key(), "DESC", -10.0, "debit", "Operating Checking", call_fn=fake_call)
    assert result.confidence == 0.0
    assert result.source == "gemini_error"
