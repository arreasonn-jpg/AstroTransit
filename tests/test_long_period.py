"""Çok sektör stitching ve uzun periyot transit keşif testleri."""

import numpy as np
import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.detection.long_period import (
    LongPeriodSearchConfig,
    LongPeriodTransitSearch,
)
from astrotransit.outputs.schemas import build_long_period_record
from astrotransit.preprocessing.stitching import stitch_detrended_light_curves
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve


def _curve(
    sector: int,
    start: float,
    end: float,
    *,
    baseline: float = 1.0,
    transit_centers: tuple[float, ...] = (),
    seed: int = 42,
) -> DetrendedLightCurve:
    rng = np.random.default_rng(seed)
    time = np.arange(start, end, 0.01)
    flux = baseline + rng.normal(0.0, 100e-6, time.size)
    for center in transit_centers:
        flux[np.abs(time - center) < 0.10] -= baseline * 0.001
    flux_err = np.full(time.size, baseline * 100e-6)
    return DetrendedLightCurve(
        target_id="TIC 900000001",
        sector=sector,
        time=time,
        flux=flux,
        flux_err=flux_err,
        trend=np.ones(time.size),
        raw_flux=flux.copy(),
        method="synthetic",
        window_length=0.5,
        break_tolerance=0.5,
    )


def test_stitching_removes_sector_offsets_and_preserves_coverage():
    stitched = stitch_detrended_light_curves(
        [
            _curve(14, 0.0, 10.0, baseline=2.0, seed=1),
            _curve(40, 100.0, 110.0, baseline=4.0, seed=2),
        ]
    )

    assert stitched.source_sectors == (14, 40)
    assert stitched.n_sectors == 2
    assert stitched.coverage_baseline_days == pytest.approx(109.99)
    assert stitched.observed_days == pytest.approx(19.98)
    assert stitched.n_gaps == 1
    assert abs(np.median(stitched.flux) - 1.0) < 0.001
    assert stitched.as_detrended().meta["source_sectors"] == [14, 40]


def test_single_transit_is_reported_as_ambiguous():
    stitched = stitch_detrended_light_curves(
        [_curve(14, 0.0, 27.0, transit_centers=(10.0,))]
    )
    result = LongPeriodTransitSearch(
        LongPeriodSearchConfig(
            min_period_days=20.0,
            max_period_days=60.0,
            min_power=5.0,
            n_durations=3,
            n_peaks=3,
        )
    ).search(stitched.as_detrended())

    assert result.has_candidate is True
    assert result.best is not None
    assert result.best.n_observed_transits == 1
    assert result.best.identifiability == "single_transit_ambiguous"
    assert any("Tek transit" in note for note in result.notes)


def test_gapped_multi_transit_prefers_a_period_with_full_coverage():
    stitched = stitch_detrended_light_curves(
        [
            _curve(14, 0.0, 27.0, transit_centers=(10.0,), seed=3),
            _curve(40, 100.0, 127.0, transit_centers=(110.0,), seed=4),
        ]
    )
    result = LongPeriodTransitSearch(
        LongPeriodSearchConfig(
            min_period_days=80.0,
            max_period_days=120.0,
            min_power=5.0,
            n_durations=3,
            n_peaks=5,
        )
    ).search(stitched.as_detrended())

    assert result.has_candidate is True
    assert result.best is not None
    assert result.best.n_observed_transits == 2
    assert result.best.n_expected_transits == 2
    assert result.best.identifiability == "multi_transit"
    assert 95.0 < result.best.period < 105.0


def test_long_period_screening_is_persistable_and_not_cascade_confirmed():
    stitched = stitch_detrended_light_curves(
        [_curve(14, 0.0, 27.0, transit_centers=(10.0,))]
    )
    result = LongPeriodTransitSearch(
        LongPeriodSearchConfig(
            min_period_days=20.0,
            max_period_days=60.0,
            min_power=5.0,
            n_durations=3,
            n_peaks=3,
        )
    ).search(stitched.as_detrended())
    record = build_long_period_record(
        result,
        stellar_props=StellarProperties(
            tic_id=900000001,
            teff=5778.0,
            radius=1.0,
            mass=1.0,
        ),
    )

    assert record is not None
    assert record.long_period_screening is True
    assert record.search_channel == "long_period"
    assert record.long_period_identifiability == "single_transit_ambiguous"
    assert record.cascade_confirmed is False
    assert record.candidate_class == "LONG_PERIOD_SINGLE_TRANSIT"
    assert record.coverage_baseline_days > 20.0
    assert record.n_observed_transits == 1
    assert record.source_sectors == "[14]"


def test_duration_grid_scales_with_stellar_properties():
    config = LongPeriodSearchConfig(
        min_period_days=20.0,
        max_period_days=500.0,
        n_durations=5,
    )
    solar = LongPeriodTransitSearch(
        config,
        stellar_radius_rsun=1.0,
        stellar_mass_msun=1.0,
    )
    compact_star = LongPeriodTransitSearch(
        config,
        stellar_radius_rsun=0.5,
        stellar_mass_msun=0.5,
    )

    assert compact_star._duration_grid()[-1] < solar._duration_grid()[-1]
    assert compact_star._search_params()["stellar_radius_rsun"] == 0.5
    assert compact_star._search_params()["stellar_mass_msun"] == 0.5
