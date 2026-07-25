from app.ingestion.normalizer import compute_dedup_key, normalize_description, parse_amount, parse_date


def test_parse_date_iso():
    assert parse_date("2026-04-01", None) == "2026-04-01"


def test_parse_date_us_slash_format():
    assert parse_date("04/01/2026", None) == "2026-04-01"


def test_parse_date_explicit_format_overrides_guessing():
    # "01/04/2026" is ambiguous; an explicit day-first format resolves it correctly.
    assert parse_date("01/04/2026", "%d/%m/%Y") == "2026-04-01"


def test_parse_date_garbage_returns_none():
    assert parse_date("not a date", None) is None


def test_parse_date_blank_returns_none():
    assert parse_date("", None) is None
    assert parse_date(None, None) is None


def test_parse_amount_plain():
    assert parse_amount("-8200.0") == -8200.0
    assert parse_amount("3425") == 3425.0


def test_parse_amount_currency_symbols_and_commas():
    assert parse_amount("$1,234.50") == 1234.50


def test_parse_amount_parentheses_means_negative():
    assert parse_amount("(1,200.00)") == -1200.00


def test_parse_amount_garbage_returns_none():
    assert parse_amount("N/A") is None


def test_parse_amount_blank_returns_none():
    assert parse_amount("") is None


def test_normalize_description_collapses_whitespace():
    assert normalize_description("  ACH   CREDIT   FOO  ") == "ACH CREDIT FOO"


def test_normalize_description_blank_is_none():
    assert normalize_description("   ") is None


def test_dedup_key_prefers_external_id():
    key = compute_dedup_key("BF-1", "2026-04-01", 100.0, "Operating Checking", "Operating Checking", "FOO")
    assert key == "id:BF-1"


def test_dedup_key_falls_back_to_content_hash_when_no_external_id():
    key1 = compute_dedup_key(None, "2026-04-01", 100.0, "Operating Checking", "Operating Checking", "FOO BAR")
    key2 = compute_dedup_key(None, "2026-04-01", 100.0, "Operating Checking", "Operating Checking", "FOO BAR")
    key3 = compute_dedup_key(None, "2026-04-02", 100.0, "Operating Checking", "Operating Checking", "FOO BAR")
    assert key1.startswith("hash:")
    assert key1 == key2
    assert key1 != key3
