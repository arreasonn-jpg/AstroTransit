"""Boundary provenance fields in radius diagnostics."""

from types import SimpleNamespace

import numpy as np

from astrotransit.validation.radius_diagnostics import build_radius_diagnostic_report


def test_fit_boundary_provenance_is_preserved() -> None:
    time = np.arange(0.0, 3.0, 0.01)
    flux = np.ones_like(time)
    candidate = SimpleNamespace(
        status="confirmed",
        tls_result=SimpleNamespace(
            period=1.0, t0=0.0, duration=0.1, depth=0.01, rp_rs=0.1, transit_count=3
        ),
    )
    fit = SimpleNamespace(
        success=True,
        fit_method="map",
        rp_rs=0.11,
        optimizer_boundary_hit=True,
        optimizer_boundary_hits=("log_rp_rs:upper", "ld_q2:lower"),
        limb_darkening_parameterization="kipping_q1_q2",
    )
    detrended = SimpleNamespace(
        time=time, flux=flux, n_points=len(time), method="biweight", window_length=0.5
    )
    sector = SimpleNamespace(sector=1, candidate=candidate, fit_result=fit, detrended=detrended)
    target = SimpleNamespace(target_id="TIC 1", stellar_props=None, sector_results=[sector])

    row = build_radius_diagnostic_report([target]).rows[0]
    assert row.fit_optimizer_boundary_hit is True
    assert row.fit_optimizer_boundary_hits == ("log_rp_rs:upper", "ld_q2:lower")
    assert row.limb_darkening_parameterization == "kipping_q1_q2"
