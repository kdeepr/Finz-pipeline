from app.classification.counterparty import extract_counterparty
from app.classification.signature import compute_signature


def test_extract_counterparty_from_job_memo():
    assert extract_counterparty("MOBILE DEPOSIT LIBERTY DAY SCHOOL JOB 4213") == "LIBERTY DAY SCHOOL"


def test_extract_counterparty_check_deposit_vs_check_dep_ordering():
    assert extract_counterparty("CHECK DEPOSIT OAK & STONE REALTY PROJECT 4501") == "OAK & STONE REALTY"
    assert extract_counterparty("CHECK DEP WEST END PHARMACY SERVICE 4214") == "WEST END PHARMACY"


def test_extract_counterparty_owner_activity_both_directions():
    assert extract_counterparty("WIRE FROM MAYA PATEL OWNER CAPITAL") == "MAYA PATEL"
    assert extract_counterparty("OWNER DISTRIBUTION MAYA PATEL") == "MAYA PATEL"


def test_signature_collapses_job_numbers_and_months():
    sig_a = compute_signature("ACH PARKSIDE COMMERCIAL MGMT RENT APR", "debit")
    sig_b = compute_signature("ACH PARKSIDE COMMERCIAL MGMT RENT MAY", "debit")
    assert sig_a == sig_b

    sig_c = compute_signature("MOBILE DEPOSIT LIBERTY DAY SCHOOL JOB 4213", "credit")
    sig_d = compute_signature("MOBILE DEPOSIT LIBERTY DAY SCHOOL JOB 6207", "credit")
    assert sig_c == sig_d


def test_signature_differs_by_direction():
    sig_credit = compute_signature("SOME DESC", "credit")
    sig_debit = compute_signature("SOME DESC", "debit")
    assert sig_credit != sig_debit
