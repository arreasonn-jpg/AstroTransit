"""
EarthTargetPoolBuilder birim testleri.

Strateji
--------
CatalogClient ve MASTClient mock'lanir. Gercek ag erisimi yok.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.data.mast_client import MASTConnectionError, MASTQueryError
from astrotransit.discovery.target_pool import (
    EarthTargetPoolBuilder,
    TargetPoolConfig,
    TargetPoolEntry,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_catalog() -> MagicMock:
    return MagicMock(name="CatalogClient")


@pytest.fixture
def mock_mast() -> MagicMock:
    return MagicMock(name="MASTClient")


@pytest.fixture
def builder(mock_catalog, mock_mast) -> EarthTargetPoolBuilder:
    return EarthTargetPoolBuilder(
        catalog_client=mock_catalog,
        mast_client=mock_mast,
    )


def _stellar(
    tic_id: int = 100,
    teff: float = 5800.0,
    radius: float = 1.05,
    mass: float = 1.0,
    tmag: float = 10.5,
    luminosity: float = 1.1,
    source: str = "TIC",
) -> StellarProperties:
    return StellarProperties(
        tic_id=tic_id, ra=45.0, dec=-20.0,
        teff=teff, logg=4.4, radius=radius, mass=mass,
        tmag=tmag, distance=50.0, luminosity=luminosity,
        metallicity=0.0, source=source,
    )


def _mock_observation_rows(sectors: list[int], tmin: float = 100.0, tmax: float = 200.0):
    """Mock observation satirlari uretir."""
    rows = []
    for s in sectors:
        row = MagicMock()
        row.colnames = ("sequence_number", "t_min", "t_max")
        row.__getitem__ = lambda self, k, s=s: {
            "sequence_number": s,
            "t_min": tmin,
            "t_max": tmax,
        }[k]
        rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────
# TargetPoolConfig
# ─────────────────────────────────────────────────────────────

def test_config_defaults_valid() -> None:
    c = TargetPoolConfig()
    c.validate()  # hata yok


def test_config_invalid_teff_range() -> None:
    c = TargetPoolConfig(min_teff_k=6000.0, max_teff_k=5000.0)
    with pytest.raises(ValueError, match="Teff"):
        c.validate()


def test_config_negative_teff() -> None:
    c = TargetPoolConfig(min_teff_k=-100.0)
    with pytest.raises(ValueError, match="Teff"):
        c.validate()


def test_config_invalid_radius_range() -> None:
    c = TargetPoolConfig(min_radius_rsun=2.0, max_radius_rsun=1.0)
    with pytest.raises(ValueError, match="yarıçap"):
        c.validate()


def test_config_invalid_tmag() -> None:
    c = TargetPoolConfig(max_tmag=0.0)
    with pytest.raises(ValueError, match="Tmag"):
        c.validate()


def test_config_invalid_min_sectors() -> None:
    c = TargetPoolConfig(min_tess_sectors=0)
    with pytest.raises(ValueError, match="Tmag"):
        c.validate()


# ─────────────────────────────────────────────────────────────
# TargetPoolEntry
# ─────────────────────────────────────────────────────────────

def test_entry_to_dict() -> None:
    e = TargetPoolEntry(
        target_id="TIC 100", tic_id=100, eligible=True,
        reasons=[], teff_k=5800.0, radius_rsun=1.05,
        sectors=(1, 2, 3), n_sectors=3,
    )
    d = e.to_dict()
    assert d["target_id"] == "TIC 100"
    assert d["tic_id"] == 100
    assert d["eligible"] is True
    assert d["sectors"] == [1, 2, 3]
    assert d["n_sectors"] == 3


def test_entry_to_dict_empty_sectors() -> None:
    e = TargetPoolEntry(target_id="TIC 1", tic_id=1)
    d = e.to_dict()
    assert d["sectors"] == []


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_builder_init_custom_clients(mock_catalog, mock_mast) -> None:
    b = EarthTargetPoolBuilder(
        catalog_client=mock_catalog, mast_client=mock_mast,
    )
    assert b.catalog_client is mock_catalog
    assert b.mast_client is mock_mast
    assert b.config is not None


def test_builder_init_validates_config(mock_catalog, mock_mast) -> None:
    bad = TargetPoolConfig(min_teff_k=-1.0)
    with pytest.raises(ValueError):
        EarthTargetPoolBuilder(config=bad, catalog_client=mock_catalog, mast_client=mock_mast)


# ─────────────────────────────────────────────────────────────
# evaluate
# ─────────────────────────────────────────────────────────────

def test_evaluate_eligible(builder) -> None:
    props = _stellar(teff=5800.0, radius=1.05, tmag=10.5)
    e = builder.evaluate(props, sectors=[1, 2])
    assert e.eligible is True
    assert e.reasons == []
    assert e.sectors == (1, 2)
    assert e.n_sectors == 2


def test_evaluate_missing_teff(builder) -> None:
    props = _stellar(teff=0.0)
    e = builder.evaluate(props)
    assert "missing_teff" in e.reasons
    assert e.eligible is False
    assert e.teff_k is None


def test_evaluate_teff_out_of_range(builder) -> None:
    props = _stellar(teff=8000.0)
    e = builder.evaluate(props)
    assert "teff_out_of_range" in e.reasons


def test_evaluate_missing_radius(builder) -> None:
    props = _stellar(radius=0.0)
    e = builder.evaluate(props)
    assert "missing_radius" in e.reasons


def test_evaluate_radius_out_of_range(builder) -> None:
    props = _stellar(radius=5.0)
    e = builder.evaluate(props)
    assert "radius_out_of_range" in e.reasons


def test_evaluate_missing_tmag(builder) -> None:
    props = _stellar(tmag=0.0)
    e = builder.evaluate(props)
    assert "missing_tmag" in e.reasons


def test_evaluate_tmag_too_faint(builder) -> None:
    props = _stellar(tmag=15.0)
    e = builder.evaluate(props)
    assert "tmag_too_faint" in e.reasons


def test_evaluate_insufficient_sectors(builder) -> None:
    props = _stellar()
    e = builder.evaluate(props, sectors=())
    assert "insufficient_tess_sectors" in e.reasons


def test_evaluate_require_stellar_mass(mock_catalog, mock_mast) -> None:
    b = EarthTargetPoolBuilder(
        config=TargetPoolConfig(require_stellar_mass=True),
        catalog_client=mock_catalog, mast_client=mock_mast,
    )
    props = _stellar(mass=0.0)
    e = b.evaluate(props)
    assert "missing_stellar_mass" in e.reasons


def test_evaluate_negative_luminosity(builder) -> None:
    props = _stellar(luminosity=-1.0)
    e = builder.evaluate(props)
    assert e.luminosity_lsun is None


# ─────────────────────────────────────────────────────────────
# build_from_tic_ids
# ─────────────────────────────────────────────────────────────

def test_build_from_tic_ids_basic(builder, mock_catalog, mock_mast) -> None:
    mock_catalog.get_stellar_properties.return_value = _stellar()
    mock_mast.query_observations.return_value = []

    entries = builder.build_from_tic_ids([100])
    assert len(entries) == 1
    # query_coverage=True ama observations bos -> sector yok
    assert "insufficient_tess_sectors" in entries[0].reasons


def test_build_from_tic_ids_with_coverage(builder, mock_catalog, mock_mast) -> None:
    mock_catalog.get_stellar_properties.return_value = _stellar()
    mock_mast.query_observations.return_value = _mock_observation_rows([1, 2, 3])

    entries = builder.build_from_tic_ids([100])
    assert entries[0].n_sectors == 3


def test_build_from_tic_ids_no_coverage(builder, mock_catalog) -> None:
    mock_catalog.get_stellar_properties.return_value = _stellar()
    entries = builder.build_from_tic_ids([100], query_coverage=False)
    # coverage sorgusu yok -> sector yok
    assert entries[0].n_sectors == 0


def test_build_from_tic_ids_catalog_exception(builder, mock_catalog) -> None:
    mock_catalog.get_stellar_properties.side_effect = RuntimeError("boom")
    entries = builder.build_from_tic_ids([100])
    assert len(entries) == 1
    assert any("catalog_error" in r for r in entries[0].reasons)


def test_build_from_tic_ids_multiple(builder, mock_catalog, mock_mast) -> None:
    mock_catalog.get_stellar_properties.return_value = _stellar()
    mock_mast.query_observations.return_value = _mock_observation_rows([1])

    entries = builder.build_from_tic_ids([100, 200, 300])
    assert len(entries) == 3


# ─────────────────────────────────────────────────────────────
# build_from_rows
# ─────────────────────────────────────────────────────────────

def test_build_from_rows_basic(builder) -> None:
    rows = [
        {"tic_id": 100, "teff": 5800.0, "radius": 1.05, "tmag": 10.5, "mass": 1.0},
    ]
    entries = builder.build_from_rows(rows)
    assert len(entries) == 1
    # query_coverage=False ve sectors verilmemis -> insufficient
    assert "insufficient_tess_sectors" in entries[0].reasons


def test_build_from_rows_with_sectors_json(builder) -> None:
    rows = [
        {
            "tic_id": 100, "teff": 5800.0, "radius": 1.05,
            "tmag": 10.5, "sectors": "[1, 2, 3]",
            "coverage_baseline_days": 27.0,
        },
    ]
    entries = builder.build_from_rows(rows)
    assert entries[0].n_sectors == 3
    assert entries[0].coverage_baseline_days == 27.0


def test_build_from_rows_with_sectors_list(builder) -> None:
    rows = [
        {"tic_id": 100, "teff": 5800.0, "radius": 1.05,
         "tmag": 10.5, "sectors": [1, 2]},
    ]
    entries = builder.build_from_rows(rows)
    assert entries[0].n_sectors == 2


def test_build_from_rows_with_coverage_query(builder, mock_mast) -> None:
    mock_mast.query_observations.return_value = _mock_observation_rows([1, 2])
    rows = [{"tic_id": 100, "teff": 5800.0, "radius": 1.05, "tmag": 10.5}]
    entries = builder.build_from_rows(rows, query_coverage=True)
    assert entries[0].n_sectors == 2


def test_build_from_rows_various_id_keys(builder) -> None:
    rows = [
        {"target_id": 100, "teff": 5800.0, "radius": 1.05, "tmag": 10.5, "sectors": [1]},
        {"tic_id": 200, "teff": 5800.0, "radius": 1.05, "tmag": 10.5, "sectors": [1]},
        {"TIC": 300, "teff": 5800.0, "radius": 1.05, "tmag": 10.5, "sectors": [1]},
    ]
    entries = builder.build_from_rows(rows)
    assert len(entries) == 3


# ─────────────────────────────────────────────────────────────
# build_from_mast_catalog
# ─────────────────────────────────────────────────────────────

def test_build_from_mast_catalog_empty(builder, mock_mast) -> None:
    mock_mast.query_tic_catalog.return_value = []
    entries = builder.build_from_mast_catalog(coordinates="0 0")
    assert entries == []


def test_build_from_mast_catalog_rows(builder, mock_mast) -> None:
    """Rows with dict benzeri Mapping'ler."""
    class FakeRow(dict):
        def __init__(self, data):
            super().__init__(data)
            self.colnames = list(data.keys())

    row = FakeRow({
        "tic_id": 100, "teff": 5800.0, "radius": 1.05,
        "tmag": 10.5, "sectors": [1],
    })
    mock_mast.query_tic_catalog.return_value = [row]
    entries = builder.build_from_mast_catalog(coordinates="0 0")
    assert len(entries) == 1


# ─────────────────────────────────────────────────────────────
# write_json / write_csv
# ─────────────────────────────────────────────────────────────

def test_write_json(builder, tmp_path: Path) -> None:
    entries = [
        TargetPoolEntry(
            target_id="TIC 100", tic_id=100, eligible=True,
            sectors=(1, 2), n_sectors=2,
        ),
    ]
    out = builder.write_json(entries, tmp_path / "pool.json")
    assert out.exists()
    data = json.loads(out.read_text())
    assert len(data) == 1
    assert data[0]["target_id"] == "TIC 100"
    assert data[0]["sectors"] == [1, 2]


def test_write_json_creates_parent_dir(builder, tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "pool.json"
    builder.write_json([], nested)
    assert nested.exists()


def test_write_csv(builder, tmp_path: Path) -> None:
    entries = [
        TargetPoolEntry(
            target_id="TIC 100", tic_id=100, eligible=True,
            reasons=["test"], sectors=(1, 2), n_sectors=2,
        ),
    ]
    out = builder.write_csv(entries, tmp_path / "pool.csv")
    assert out.exists()
    with out.open() as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["target_id"] == "TIC 100"
    # JSON-encoded alanlar
    assert json.loads(rows[0]["sectors"]) == [1, 2]
    assert json.loads(rows[0]["reasons"]) == ["test"]


def test_write_csv_empty(builder, tmp_path: Path) -> None:
    out = builder.write_csv([], tmp_path / "empty.csv")
    assert out.exists()
    # Sadece header
    with out.open() as f:
        lines = f.readlines()
    assert len(lines) == 1


# ─────────────────────────────────────────────────────────────
# _query_coverage
# ─────────────────────────────────────────────────────────────

def test_query_coverage_connection_error(builder, mock_mast) -> None:
    mock_mast.query_observations.side_effect = MASTConnectionError("offline")
    sectors, _baseline = builder._query_coverage("TIC 100")
    assert sectors == ()


def test_query_coverage_query_error(builder, mock_mast) -> None:
    mock_mast.query_observations.side_effect = MASTQueryError("timeout")
    sectors, _baseline = builder._query_coverage("TIC 100")
    assert sectors == ()


def test_query_coverage_empty(builder, mock_mast) -> None:
    mock_mast.query_observations.return_value = []
    sectors, baseline = builder._query_coverage("TIC 100")
    assert sectors == ()
    assert baseline is None


def test_query_coverage_sectors_and_baseline(builder, mock_mast) -> None:
    mock_mast.query_observations.return_value = _mock_observation_rows(
        [1, 2, 3], tmin=100.0, tmax=130.0,
    )
    sectors, baseline = builder._query_coverage("TIC 100")
    assert sectors == (1, 2, 3)
    assert baseline == 30.0


# ─────────────────────────────────────────────────────────────
# _sectors_from_value
# ─────────────────────────────────────────────────────────────

def test_sectors_from_none() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value(None) == ()


def test_sectors_from_empty_string() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value("") == ()


def test_sectors_from_json_string() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value("[1, 2, 3]") == (1, 2, 3)


def test_sectors_from_csv_string() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value("1,2,3") == (1, 2, 3)


def test_sectors_from_semicolon_string() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value("1;2;3") == (1, 2, 3)


def test_sectors_from_list() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value([1, 2]) == (1, 2)


def test_sectors_from_single_int_returns_empty() -> None:
    """Tek int iterate edilemedigi icin TypeError yakalanir ve () doner.

    Not: gercek kullanimda sectors genellikle liste/tuple/JSON string olarak
    verilir; tek int degeri desteklenmiyor.
    """
    assert EarthTargetPoolBuilder._sectors_from_value(5) == ()


def test_sectors_from_invalid() -> None:
    assert EarthTargetPoolBuilder._sectors_from_value("abc") == ()


# ─────────────────────────────────────────────────────────────
# _optional_float
# ─────────────────────────────────────────────────────────────

def test_optional_float_valid() -> None:
    assert EarthTargetPoolBuilder._optional_float(27.5) == 27.5
    assert EarthTargetPoolBuilder._optional_float("27.5") == 27.5


def test_optional_float_zero_or_negative() -> None:
    assert EarthTargetPoolBuilder._optional_float(0.0) is None
    assert EarthTargetPoolBuilder._optional_float(-5.0) is None


def test_optional_float_none() -> None:
    assert EarthTargetPoolBuilder._optional_float(None) is None


def test_optional_float_invalid() -> None:
    assert EarthTargetPoolBuilder._optional_float("abc") is None


# ─────────────────────────────────────────────────────────────
# _properties_from_row
# ─────────────────────────────────────────────────────────────

def test_properties_from_row_basic() -> None:
    row = {"teff": 5800.0, "radius": 1.05, "mass": 1.0, "tmag": 10.5}
    props = EarthTargetPoolBuilder._properties_from_row(row, 100)
    assert props.tic_id == 100
    assert props.teff == 5800.0
    assert props.radius == 1.05
    assert props.mass == 1.0
    assert props.tmag == 10.5


def test_properties_from_row_alternative_keys() -> None:
    row = {"Teff": 5800.0, "rad": 1.05, "Tmag": 10.5}
    props = EarthTargetPoolBuilder._properties_from_row(row, 100)
    assert props.teff == 5800.0
    assert props.radius == 1.05
    assert props.tmag == 10.5


def test_properties_from_row_missing() -> None:
    row = {}
    props = EarthTargetPoolBuilder._properties_from_row(row, 100)
    assert props.teff == 0.0
    assert props.radius == 0.0


def test_properties_from_row_invalid_values() -> None:
    row = {"teff": "abc", "radius": None}
    props = EarthTargetPoolBuilder._properties_from_row(row, 100)
    assert props.teff == 0.0
    assert props.radius == 0.0


def test_properties_from_row_with_source() -> None:
    row = {"teff": 5800.0, "source": "custom"}
    props = EarthTargetPoolBuilder._properties_from_row(row, 100)
    assert props.source == "custom"
