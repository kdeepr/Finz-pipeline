from app.db import get_db
from app.qbo.account_ids import AccountMappingError, build_mapping_from_qbo_accounts, get_qbo_id

# `_fresh_mongomock` (autouse, in conftest.py) resets Mongo before every test in
# this file automatically - no fixture needs to be requested explicitly.


def test_matches_by_acctnum_first():
    db = get_db()
    qbo_accounts = [{"Id": "80", "Name": "Repair Income", "AcctNum": "4000"}]
    our_chart = [{"Account No.": "4000", "Account Name": "Repair Service Revenue"}]
    unmatched = build_mapping_from_qbo_accounts(db, qbo_accounts, our_chart)
    assert unmatched == []
    assert get_qbo_id(db, "4000") == "80"


def test_falls_back_to_name_when_acctnum_missing():
    db = get_db()
    qbo_accounts = [{"Id": "81", "Name": "Repair Service Revenue"}]  # no AcctNum set in sandbox
    our_chart = [{"Account No.": "4000", "Account Name": "Repair Service Revenue"}]
    unmatched = build_mapping_from_qbo_accounts(db, qbo_accounts, our_chart)
    assert unmatched == []
    assert get_qbo_id(db, "4000") == "81"


def test_reports_unmatched_accounts_instead_of_silently_skipping():
    db = get_db()
    qbo_accounts = [{"Id": "80", "Name": "Something Else", "AcctNum": "9999"}]
    our_chart = [{"Account No.": "4000", "Account Name": "Repair Service Revenue"}]
    unmatched = build_mapping_from_qbo_accounts(db, qbo_accounts, our_chart)
    assert unmatched == ["4000"]


def test_get_qbo_id_raises_clear_error_when_not_synced():
    db = get_db()
    try:
        get_qbo_id(db, "4000")
        assert False, "expected AccountMappingError"
    except AccountMappingError as exc:
        assert "accounts/sync" in str(exc)
