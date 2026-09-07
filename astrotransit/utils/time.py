"""
Zaman dönüşüm yardımcıları.

TESS ve JWST zaman sistemleri arasında dönüşüm sağlar.
"""

from __future__ import annotations

from astropy.time import Time


# TESS Barycentric Julian Date offset
# TESS BJD = BJD - 2457000.0
TESS_BJD_OFFSET = 2457000.0

# JWST Modified Julian Date offset
JWST_MJD_OFFSET = 2400000.5


def tess_bjd_to_jd(tess_bjd: float) -> float:
    """
    TESS BJD'yi standart Julian Date'e çevirir.

    TESS zaman serilerinde zamanlar BTJD (Barycentric TESS Julian Date)
    formatındadır: BTJD = BJD - 2457000.0

    Parameters
    ----------
    tess_bjd : float
        TESS BJD değeri.

    Returns
    -------
    float
        Standart Julian Date.
    """

    return tess_bjd + TESS_BJD_OFFSET


def jd_to_tess_bjd(jd: float) -> float:
    """Standart Julian Date'i TESS BJD'ye çevirir."""

    return jd - TESS_BJD_OFFSET


def jd_to_iso(jd: float) -> str:
    """Julian Date'i ISO 8601 formatına çevirir."""

    t = Time(jd, format="jd", scale="tdb")
    return t.iso


def iso_to_jd(iso_str: str) -> float:
    """ISO 8601 tarihini Julian Date'e çevirir."""

    t = Time(iso_str, format="iso", scale="utc")
    return t.jd