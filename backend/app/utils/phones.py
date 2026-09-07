"""
Canonical phone normalization (Wave 27 — WhatsApp).

`normalize_phone_to_e164` is the ONLY normalization logic the codebase uses for
WhatsApp matching/sending (documents recipient authority, inbound client
matching). It never guesses a country code: a bare local number without an
international prefix is treated as NOT matchable.
"""

import re
from typing import Optional


def normalize_phone_to_e164(raw: Optional[str]) -> Optional[str]:
    """Normalize a phone string to canonical E.164 (``+<digits>``) or None.

    - Trims whitespace; strips internal spaces/dashes/parens/dots.
    - ``+<country><number>`` is kept (existing international prefix).
    - Leading ``00`` is replaced with ``+`` (international prefix).
    - Anything else (bare local numbers, garbage) -> None. No country guessing.
    """
    if raw is None:
        return None
    cleaned = re.sub(r"[\s\-().]+", "", str(raw).strip())
    if not cleaned:
        return None
    if cleaned.startswith("+"):
        digits = cleaned[1:]
    elif cleaned.startswith("00"):
        digits = cleaned[2:]
    else:
        return None
    if not digits or not digits.isdigit():
        return None
    if len(digits) < 8 or len(digits) > 15:
        return None
    return "+" + digits
