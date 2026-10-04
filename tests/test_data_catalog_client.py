"""
CatalogClient birim testleri.

Strateji
--------
MASTClient ve Simbad monkeypatch ile mock'lanir.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from astropy.table import Table

from astrotransit.data import catalog_client as cc_module
from astrotransit.data.catalog_client import CatalogClient, StellarProperties
from astrotransit.data.mast_client import MASTConnectionError, MASTQueryError

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_mast() -> MagicMock:
    return MagicMock(name="MASTClient")


@pytest.fixture
def client(mock_mast, monkeypatch) -> CatalogClient:
    monkeypatch.setattr(cc_module, "MASTClient", lambda: mock_mast)
    return CatalogClient()


def _tic_table(
    ra=45.0, dec=-20.0, teff=5800.0, logg=4.4,
    rad=1.05, mass=1.0, tmag=10.5, d=50.0, lum=1.1, mh=0.0,
) -> Table:
    return Table({
        "ra": [ra],
        "dec": [dec],
        "Teff": [teff],
        "logg": [logg],
        "rad": [rad],
        "mass": [mass],
        "Tmag": [tmag],
        "d": [d],
        "lum": [lum],
        "MH": [mh],
    })


# ─────────────────────────────────────────────────────────────
# StellarProperties
# ─────────────────────────────────────────────────────────────

def test_stellar_properties_defaults() -> None:
    p = StellarProperties()
    assert p.tic_id == 0
    assert p.teff == 0.0
    assert p.source == ""
    assert p.extra == {}


def test_stellar_properties_is_valid_true() -> None:
    p = StellarProperties(teff=5800.0, radius=1.05)
    assert p.is_valid() is True


def test_stellar_properties_is_valid_false_when_teff_zero() -> None:
    p = StellarProperties(teff=0.0, radius=1.05)
    assert p.is_valid() is False


def test_stellar_properties_is_valid_false_when_radius_zero() -> None:
    p = StellarProperties(teff=5800.0, radius=0.0)
    assert p.is_valid() is False


def test_stellar_properties_to_dict() -> None:
    p = StellarProperties(
        tic_id=100, ra=45.0, dec=-20.0, teff=5800.0,
        logg=4.4, radius=1.05, mass=1.0, tmag=10.5,
        distance=50.0, luminosity=1.1, metallicity=0.0, source="TIC",
    )
    d = p.to_dict()
    assert d["tic_id"] == 100
    assert d["teff"] == 5800.0
    assert d["radius_rsun"] == 1.05
    assert d["mass_msun"] == 1.0
    assert d["source"] == "TIC"


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_client_init(mock_mast, monkeypatch) -> None:
    monkeypatch.setattr(cc_module, "MASTClient", lambda: mock_mast)
    c = CatalogClient()
    assert c._mast is mock_mast


# ─────────────────────────────────────────────────────────────
# get_stellar_properties
# ─────────────────────────────────────────────────────────────

def test_get_stellar_properties_success(client, mock_mast) -> None:
    mock_mast.query_tic_catalog.return_value = _tic_table()
    p = client.get_stellar_properties(12345)
    assert p.tic_id == 12345
    assert p.teff == 5800.0
    assert p.radius == 1.05
    assert p.source == "TIC"
    assert p.is_valid() is True


def test_get_stellar_properties_accepts_str(client, mock_mast) -> None:
    mock_mast.query_tic_catalog.return_value = _tic_table()
    p = client.get_stellar_properties("TIC 12345")
    assert p.tic_id == 12345
    mock_mast.query_tic_catalog.assert_called_once_with(tic_id=12345)


def test_get_stellar_properties_mast_connection_error(client, mock_mast) -> None:
    mock_mast.query_tic_catalog.side_effect = MASTConnectionError("offline")
    p = client.get_stellar_properties(999)
    assert p.tic_id == 999
    assert p.source == "failed"


def test_get_stellar_properties_mast_query_error(client, mock_mast) -> None:
    mock_mast.query_tic_catalog.side_effect = MASTQueryError("timeout")
    p = client.get_stellar_properties(999)
    assert p.source == "failed"


def test_get_stellar_properties_empty_table(client, mock_mast) -> None:
    mock_mast.query_tic_catalog.return_value = Table()
    p = client.get_stellar_properties(999)
    assert p.tic_id == 999
    assert p.source == "not_found"


def test_get_stellar_properties_invalid_values(client, mock_mast) -> None:
    """Teff=0 (invalid) -> warning yazilir, source hala TIC."""
    mock_mast.query_tic_catalog.return_value = _tic_table(teff=0.0, rad=0.0)
    p = client.get_stellar_properties(1)
    assert p.source == "TIC"
    assert p.is_valid() is False


# ─────────────────────────────────────────────────────────────
# query_simbad
# ─────────────────────────────────────────────────────────────

def test_query_simbad_none_when_unavailable(client, monkeypatch) -> None:
    monkeypatch.setattr(cc_module, "Simbad", None)
    result = client.query_simbad("TIC 1")
    assert result is None


def test_query_simbad_success(client, monkeypatch) -> None:
    fake_simbad = MagicMock()
    fake_instance = MagicMock()
    fake_result = MagicMock()
    fake_instance.query_object.return_value = fake_result
    fake_simbad.return_value = fake_instance
    monkeypatch.setattr(cc_module, "Simbad", fake_simbad)

    result = client.query_simbad("TIC 1")
    assert result is fake_result
    fake_instance.add_votable_fields.assert_called_once()


def test_query_simbad_returns_none_on_miss(client, monkeypatch) -> None:
    fake_simbad = MagicMock()
    fake_instance = MagicMock()
    fake_instance.query_object.return_value = None
    fake_simbad.return_value = fake_instance
    monkeypatch.setattr(cc_module, "Simbad", fake_simbad)

    result = client.query_simbad("not real")
    assert result is None


def test_query_simbad_exception_handled(client, monkeypatch) -> None:
    fake_simbad = MagicMock()
    fake_instance = MagicMock()
    fake_instance.query_object.side_effect = RuntimeError("network")
    fake_simbad.return_value = fake_instance
    monkeypatch.setattr(cc_module, "Simbad", fake_simbad)

    result = client.query_simbad("X")
    assert result is None


# ─────────────────────────────────────────────────────────────
# _safe_float
# ─────────────────────────────────────────────────────────────

def test_safe_float_normal() -> None:
    row = {"x": 42.5}
    assert CatalogClient._safe_float(row, "x") == 42.5


def test_safe_float_missing_key() -> None:
    row = {"y": 1.0}
    assert CatalogClient._safe_float(row, "x") == 0.0


def test_safe_float_none_value() -> None:
    row = {"x": None}
    assert CatalogClient._safe_float(row, "x") == 0.0


def test_safe_float_with_default() -> None:
    row = {"y": 1.0}
    assert CatalogClient._safe_float(row, "x", default=-1.0) == -1.0


def test_safe_float_non_numeric() -> None:
    row = {"x": "abc"}
    assert CatalogClient._safe_float(row, "x") == 0.0


def test_safe_float_nan() -> None:
    row = {"x": float("nan")}
    assert CatalogClient._safe_float(row, "x") == 0.0


def test_safe_float_masked_value() -> None:
    masked = MagicMock()
    masked.mask = True
    row = {"x": masked}
    assert CatalogClient._safe_float(row, "x") == 0.0


def test_safe_float_int_value() -> None:
    row = {"x": 42}
    assert CatalogClient._safe_float(row, "x") == 42.0
