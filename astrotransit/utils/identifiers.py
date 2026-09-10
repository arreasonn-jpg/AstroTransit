"""
Hedef tanımlayıcı yardımcıları.

TIC ID, TOI numarası gibi tanımlayıcıları ayrıştırır ve standartlaştırır.
"""

from __future__ import annotations

import math
import re
from numbers import Integral


def normalize_tic_id(raw: str | int) -> str:
    """
    TIC ID'yi standart formata getirir.

    Yalnızca pozitif tam sayılar ile ``TIC`` önekli/öneksiz sayısal
    dizgiler kabul edilir. Böylece ``abc123`` gibi bozuk tanımlayıcıların
    sessizce geçerli bir TIC ID'ye dönüşmesi engellenir.

    Örnekler
    --------
    >>> normalize_tic_id("TIC 123456789")
    'TIC 123456789'
    >>> normalize_tic_id("tic123456789")
    'TIC 123456789'
    >>> normalize_tic_id(123456789)
    'TIC 123456789'
    """

    if isinstance(raw, bool):
        raise ValueError("TIC ID bool olamaz.")

    if isinstance(raw, Integral):
        number = int(raw)
    elif isinstance(raw, str):
        match = re.fullmatch(
            r"(?:TIC[\s-]*)?(\d+)",
            raw.strip(),
            flags=re.IGNORECASE,
        )
        if match is None:
            raise ValueError(f"Geçersiz TIC ID: '{raw}'")
        number = int(match.group(1))
    else:
        raise TypeError("TIC ID str veya integer olmalıdır.")

    if number <= 0:
        raise ValueError("TIC ID pozitif olmalıdır.")

    return f"TIC {number}"


def extract_tic_number(tic_id: str) -> int:
    """
    TIC ID'den sayısal değeri çıkarır.

    >>> extract_tic_number("TIC 123456789")
    123456789
    """

    normalized = normalize_tic_id(tic_id)
    return int(normalized.removeprefix("TIC "))


def normalize_toi_id(raw: str | float) -> str:
    """
    TOI numarasını standart formata getirir.

    Yalnızca sonlu, pozitif sayılar ile ``TOI`` önekli/öneksiz sayısal
    dizgiler kabul edilir.

    >>> normalize_toi_id("TOI-1234.01")
    'TOI-1234.01'
    >>> normalize_toi_id(1234.01)
    'TOI-1234.01'
    """

    if isinstance(raw, bool):
        raise ValueError("TOI ID bool olamaz.")

    if isinstance(raw, (int, float)):
        numeric = float(raw)
        if not math.isfinite(numeric) or numeric <= 0:
            raise ValueError("TOI ID sonlu ve pozitif olmalıdır.")
        value = str(raw)
    elif isinstance(raw, str):
        match = re.fullmatch(
            r"(?:TOI[\s-]*)?(\d+(?:\.\d+)?)",
            raw.strip(),
            flags=re.IGNORECASE,
        )
        if match is None:
            raise ValueError(f"Geçersiz TOI ID: '{raw}'")
        value = match.group(1)
    else:
        raise TypeError("TOI ID str veya sayı olmalıdır.")

    return f"TOI-{value}"
