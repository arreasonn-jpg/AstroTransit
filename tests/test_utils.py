"""Yardımcı modül testleri."""

import pytest

from astrotransit.utils.identifiers import (
    normalize_tic_id,
    extract_tic_number,
    normalize_toi_id,
)
from astrotransit.utils.time import (
    tess_bjd_to_jd,
    jd_to_tess_bjd,
    jd_to_iso,
)


class TestNormalizeTicId:
    """TIC ID normalizasyon testleri."""

    def test_integer_input(self):
        assert normalize_tic_id(123456789) == "TIC 123456789"

    def test_string_with_prefix(self):
        assert normalize_tic_id("TIC 123456789") == "TIC 123456789"

    def test_string_without_prefix(self):
        assert normalize_tic_id("123456789") == "TIC 123456789"

    def test_string_lowercase(self):
        assert normalize_tic_id("tic123456789") == "TIC 123456789"

    def test_string_with_spaces(self):
        assert normalize_tic_id("  TIC  123456789  ") == "TIC 123456789"

    def test_invalid_input(self):
        with pytest.raises(ValueError):
            normalize_tic_id("abc")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            normalize_tic_id("")


class TestExtractTicNumber:
    """TIC sayı çıkartma testleri."""

    def test_standard(self):
        assert extract_tic_number("TIC 123456789") == 123456789

    def test_from_integer(self):
        assert extract_tic_number("261136679") == 261136679


class TestNormalizeToi:
    """TOI normalizasyon testleri."""

    def test_float_input(self):
        assert normalize_toi_id(1234.01) == "TOI-1234.01"

    def test_string_input(self):
        assert normalize_toi_id("TOI-1234.01") == "TOI-1234.01"


class TestTimeConversions:
    """Zaman dönüşüm testleri."""

    def test_tess_bjd_roundtrip(self):
        original = 1000.5
        jd = tess_bjd_to_jd(original)
        back = jd_to_tess_bjd(jd)
        assert abs(back - original) < 1e-10

    def test_tess_bjd_offset(self):
        jd = tess_bjd_to_jd(0.0)
        assert abs(jd - 2457000.0) < 1e-10

    def test_jd_to_iso(self):
        iso = jd_to_iso(2459000.5)
        assert "2020" in iso