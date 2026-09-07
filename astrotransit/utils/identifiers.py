"""
Hedef tanımlayıcı yardımcıları.

TIC ID, TOI numarası gibi tanımlayıcıları ayrıştırır ve standartlaştırır.
"""

from __future__ import annotations

import re
from numbers import Integral


def normalize_tic_id(raw: str | int) -> str:
    """
    TIC ID'yi standart formata getirir.

    Örnekler
    --------
    >>> normalize_tic_id("TIC 123456789")
    'TIC 123456789'
    >>> normalize_tic_id("tic123456789")
    'TIC 123456789'
    >>> normalize_tic_id(123456789)
    'TIC 123456789'
    """

    if isinstance(raw, Integral):
        return f"TIC {int(raw)}"

    cleaned = raw.strip().upper().replace("TIC", "").replace("-", "").strip()
    digits = re.sub(r"\D", "", cleaned)

    if not digits:
        raise ValueError(f"Geçersiz TIC ID: '{raw}'")

    return f"TIC {int(digits)}"


def extract_tic_number(tic_id: str) -> int:
    """
    TIC ID'den sayısal değeri çıkarır.

    >>> extract_tic_number("TIC 123456789")
    123456789
    """

    normalized = normalize_tic_id(tic_id)
    return int(normalized.replace("TIC ", ""))


def normalize_toi_id(raw: str | float) -> str:
    """
    TOI numarasını standart formata getirir.

    >>> normalize_toi_id("TOI-1234.01")
    'TOI-1234.01'
    >>> normalize_toi_id(1234.01)
    'TOI-1234.01'
    """

    if isinstance(raw, (int, float)):
        return f"TOI-{raw}"

    cleaned = raw.strip().upper().replace("TOI", "").replace("-", "").strip()

    if not cleaned:
        raise ValueError(f"Geçersiz TOI ID: '{raw}'")

    return f"TOI-{cleaned}"