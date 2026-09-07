"""Yeni discovery/validation/çıktı sözleşmeleri için hızlı contract testleri."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from astrotransit.discovery.target_pool import EarthTargetPoolBuilder, TargetPoolConfig
from astrotransit.outputs.migration import migrate_json, migrate_parquet
from astrotransit.outputs.schemas import SCHEMA_VERSION
from astrotransit.science.earth_similarity import score_earth_similarity
from astrotransit.pipelines.jwst_pipeline import (
    JWSTFollowUpResult,
    JWSTObservationResult,
    JWSTProductContract,
    load_jwst_product,
)
from astrotransit.validation.adapters import (
    RVFollowupMeasurement,
    TransitFollowupMeasurement,
    rv_measurement_to_evidence,
    transit_measurement_to_evidence,
)
from astrotransit.validation.fpp_benchmark import FPPBenchmarkCase, evaluate_fpp_benchmark
from astrotransit.validation.injection_recovery import (
    InjectionScenario,
    inject_box_transit,
    run_injection_recovery,
)


def test_target_pool_filters_catalog_rows_without_network() -> None:
    builder = EarthTargetPoolBuilder(TargetPoolConfig(max_tmag=12.0))
    entries = builder.build_from_rows(
        [
            {
                "tic_id": 123,
                "teff": 5778,
                "radius": 1.0,
                "mass": 1.0,
                "tmag": 10.0,
                "sectors": [1, 2],
                "coverage_baseline_days": 54.0,
            },
            {"tic_id": 456, "teff": 7000, "radius": 1.0, "tmag": 10.0, "sectors": [1]},
        ]
    )

    assert entries[0].eligible is True
    assert entries[0].sectors == (1, 2)
    assert entries[1].eligible is False
    assert "teff_out_of_range" in entries[1].reasons


def test_injection_recovery_requires_period_match() -> None:
    time = np.linspace(0.0, 12.0, 2400)
    flux = np.ones_like(time)
    scenario = InjectionScenario(3.0, 0.01, 0.12, 0.25, label="small")
    injected = inject_box_transit(time, flux, scenario)
    assert np.min(injected) == pytest.approx(0.99)

    report = run_injection_recovery(
        time,
        flux,
        [scenario],
        detector=lambda _time, _flux: {"period": 3.01},
    )
    assert report.n_trials == 1
    assert report.n_recovered == 1
    assert report.completeness_by_label["small"] == 1.0


def test_fpp_benchmark_reports_calibration_and_confusion() -> None:
    report = evaluate_fpp_benchmark(
        [
            FPPBenchmarkCase("fp", True, 0.9),
            FPPBenchmarkCase("planet", False, 0.1),
        ]
    )
    assert report.brier_score == pytest.approx(0.01)
    assert report.false_positive_recall == 1.0
    assert report.planet_precision == 1.0
    assert report.confusion_matrix["true_positive_fp"] == 1


def test_followup_adapters_do_not_confirm_low_quality_measurements() -> None:
    rv = rv_measurement_to_evidence(
        RVFollowupMeasurement("HARPS", ("a", "b"), 2.0, 1.0, n_epochs=2)
    )
    assert rv.confirmed is False
    transit = transit_measurement_to_evidence(
        TransitFollowupMeasurement("ground", ("a",), 10.0, period_consistent=True, snr=20)
    )
    assert transit.confirmed is False


def test_earth_similarity_uncertainty_is_reproducible() -> None:
    kwargs = {
        "planet_radius_rearth": 1.0,
        "insolation_s_earth": 1.0,
        "equilibrium_temperature_k": 255.0,
        "semi_major_axis_au": 1.0,
        "stellar_teff_k": 5778.0,
        "errors": {"planet_radius_rearth": 0.05, "insolation": 0.1},
        "n_samples": 300,
        "random_seed": 7,
    }
    first = score_earth_similarity("photometric_earth_analog", **kwargs)
    second = score_earth_similarity("photometric_earth_analog", **kwargs)
    assert first.uncertainty_available is True
    assert first.to_dict() == second.to_dict()
    assert first.score_p05 <= first.score_p50 <= first.score_p95


def test_jwst_product_contract_rejects_missing_product(tmp_path: Path) -> None:
    contract = JWSTProductContract(
        tmp_path / "missing.fits", "TIC 1", "obs-1", "1234", "NIRISS"
    )
    observation, validation = load_jwst_product(contract)
    assert observation is None
    assert validation.valid is False
    assert "bulunamadı" in validation.error


def test_jwst_product_contract_loads_valid_fits(tmp_path: Path) -> None:
    from astropy.io import fits

    path = tmp_path / "jwst_stage3.fits"
    time = np.linspace(2459000.0, 2459000.2, 24)
    columns = fits.ColDefs(
        [
            fits.Column(name="TIME", format="D", array=time),
            fits.Column(name="FLUX", format="D", array=np.ones(24)),
            fits.Column(name="FLUX_ERR", format="D", array=np.full(24, 1e-4)),
        ]
    )
    fits.BinTableHDU.from_columns(columns).writeto(path)
    contract = JWSTProductContract(path, "TIC 1", "obs-1", "1234", "NIRISS")
    observation, validation = load_jwst_product(contract)
    assert validation.valid is True
    assert validation.n_points == 24
    assert observation is not None
    assert observation.n_points == 24


def test_jwst_placeholder_cannot_be_confirmed() -> None:
    result = JWSTFollowUpResult(
        target_id="TIC 1",
        results=[JWSTObservationResult(program_id="1234", observation_id="obs-1", success=True)],
        success=True,
    )
    with pytest.raises(ValueError, match="transit_confirmed"):
        result.to_followup_evidence(confirmed=True)


def test_json_and_parquet_migration_upgrade_schema(tmp_path: Path) -> None:
    old_payload = {
        "metadata": {"schema_version": "1.2", "created_at": "2020-01-01T00:00:00Z"},
        "target": {"source_id": "TIC 123", "tic_id": 123, "sector": 1},
        "stellar": {"teff_k": 5778, "radius_rsun": 1.0, "tmag": 10.0},
        "parameters": {"period_days": 365.0, "depth_ppm": 84.0},
        "earth_similarity": {"score": 91.0, "classification": "EARTH_TWIN_CANDIDATE"},
        "followup": {"confirmed": False},
    }
    source = tmp_path / "old.json"
    source.write_text(json.dumps(old_payload), encoding="utf-8")
    migrated = migrate_json(source, tmp_path / "new.json")
    payload = json.loads(migrated.read_text(encoding="utf-8"))
    assert payload["metadata"]["schema_version"] == SCHEMA_VERSION
    assert payload["earth_similarity"]["score"] == 91.0
    assert "equilibrium_temperature_albedo" in payload["derived"]

    pa = pytest.importorskip("pyarrow")
    import pyarrow.parquet as pq

    old_parquet = tmp_path / "old.parquet"
    pq.write_table(pa.Table.from_pylist([{"source_id": "TIC 123", "sector": 1}],), old_parquet)
    new_parquet = migrate_parquet(old_parquet, tmp_path / "new.parquet")
    table = pq.read_table(new_parquet)
    assert table.schema.field("schema_version") is not None
    assert table.column("schema_version").to_pylist() == [SCHEMA_VERSION]
