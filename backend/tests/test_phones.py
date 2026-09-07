"""Wave 27 — canonical phone normalization tests.

`normalize_phone_to_e164` is the ONLY normalization the WhatsApp flow is
allowed to use. It never guesses a country code: bare local numbers are not
matchable. Covers the E.164 upper/lower bounds (8-15 digits), the ``00``
international prefix rewrite, strip characters, and garbage/None inputs.
"""

from app.utils.phones import normalize_phone_to_e164


def test_keeps_existing_international_prefix():
    assert normalize_phone_to_e164("+971501234567") == "+971501234567"


def test_strips_internal_spaces_dashes_parens_dots():
    assert normalize_phone_to_e164("+97 1501-2345-67") == "+971501234567"
    assert normalize_phone_to_e164("+(971) 50 123.4567") == "+971501234567"


def test_rewrites_double_zero_prefix_to_plus():
    assert normalize_phone_to_e164("00971501234567") == "+971501234567"


def test_bare_local_number_never_guessed():
    assert normalize_phone_to_e164("0501234567") is None
    assert normalize_phone_to_e164("501234567") is None


def test_bounds_min_and_max_digits():
    assert normalize_phone_to_e164("+12345678") == "+12345678"  # 8 digits (min)
    assert normalize_phone_to_e164("+123456789012345") == "+123456789012345"  # 15 (max)
    assert normalize_phone_to_e164("+1234567") is None  # 7 digits
    assert normalize_phone_to_e164("+1234567890123456") is None  # 16 digits


def test_garbage_and_empty():
    assert normalize_phone_to_e164(None) is None
    assert normalize_phone_to_e164("") is None
    assert normalize_phone_to_e164("   ") is None
    assert normalize_phone_to_e164("+") is None
    assert normalize_phone_to_e164("+abcdefgh") is None
    assert normalize_phone_to_e164("00501234567only") is None


def test_edge_leading_zero_after_prefix_is_kept():
    # The util is lenient: a +0 prefix is kept verbatim (no country guessing).
    assert normalize_phone_to_e164("+0501234567") == "+0501234567"
