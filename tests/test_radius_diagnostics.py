"""TLS-versus-MAP radius diagnostic contract tests."""

from types import SimpleNamespace

import numpy as np
import pytest

from astrotransit.validation.radius_diagnostics import (
    build_radius_diagnostic_report,
    estimate_detrended_depth,
    write_radius_diagnostic_report,
)


def _detrended() -> SimpleNamespace:
    time = np.arange(0.0, 4.0, 0.01)
    phase = ((time + 0.5) % 1.0) - 0.5
    flux = np.ones_like(time)
    flux[np.abs(phase) <= 0.05] = 0.99
    return SimpleNamespace(
        time=time,
        flux=flux,
        n_points=len(time),
        method="biweight",
        window_length=0.5,
    )


def test_estimate_detrended_depth_uses_local_out_of_transit_baseline() -> None:
    depth, n_in, n_baseline = estimate_detrended_depth(
        _detrended(), period=1.0, t0=0.0, duration=0.1
    )
    assert depth == pytest.approx(0.01)
    assert n_in > 2
    assert n_baseline > 5


def test_report_keeps_tls_and_map_quantities_separate(tmp_path) -> None:
    detrended = _detrended()
    tls = SimpleNamespace(
        period=1.0,
        t0=0.0,
        duration=0.1,
        depth=0.01,
        rp_rs=0.1,
        transit_count=4,
    )
    candidate = SimpleNamespace(tls_result=tls, status="confirmed")
    fit = SimpleNamespace(
        success=True,
        fit_method="map",
        rp_rs=0.12,
        u1=0.3,
        u2=0.2,
        impact_parameter=0.4,
        a_over_rs=8.0,
        baseline=1.0,
        log_jitter=-7.0,
        residual_rms=0.001,
        derived=SimpleNamespace(planet_radius_rearth=2.5),
    )
    sector = SimpleNamespace(
        target_id="TIC 123",
        sector=5,
        candidate=candidate,
        fit_result=fit,
        detrended=detrended,
    )
    target = SimpleNamespace(
        target_id="TIC 123",
        stellar_props=SimpleNamespace(radius=0.9, source="TIC v8"),
        sector_results=[sector],
    )

    report = build_radius_diagnostic_report(
        [target], configured_cadence_seconds=120.0
    )
    row = report.rows[0]
    assert row.comparison_status == "evaluated"
    assert row.tls_rp_rs == pytest.approx(0.1)
    assert row.fit_rp_rs == pytest.approx(0.12)
    assert row.rp_rs_fractional_delta_vs_tls == pytest.approx(0.2)
    assert row.detrended_depth_ppm == pytest.approx(10000.0)
    assert report.to_dict()["summary"]["n_evaluated"] == 1

    json_path, csv_path = write_radius_diagnostic_report(report, tmp_path)
    assert json_path.exists()
    assert csv_path.exists()
    assert "NaN" not in json_path.read_text(encoding="utf-8")


def test_missing_fit_is_explicitly_not_evaluated() -> None:
    tls = SimpleNamespace(period=1.0, t0=0.0, duration=0.1, depth=0.01, rp_rs=0.1)
    sector = SimpleNamespace(
        sector=1,
        candidate=SimpleNamespace(tls_result=tls, status="confirmed"),
        fit_result=None,
        detrended=_detrended(),
    )
    target = SimpleNamespace(target_id="TIC 9", stellar_props=None, sector_results=[sector])
    report = build_radius_diagnostic_report([target])
    assert report.rows[0].comparison_status == "not_evaluated_missing_fit"
    assert report.to_dict()["summary"]["n_not_evaluated"] == 1
