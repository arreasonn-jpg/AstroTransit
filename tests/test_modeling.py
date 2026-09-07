"""Modelleme modülü testleri."""

import numpy as np
import pytest


class TestParameters:
    """Parametre hesaplama testleri."""

    def test_derived_parameters(self):
        from astrotransit.modeling.parameters import compute_derived_parameters

        derived = compute_derived_parameters(
            period=3.5,
            rp_rs=0.1,
            impact_parameter=0.3,
            duration=0.1,
            stellar_radius=1.0,
            stellar_mass=1.0,
            stellar_teff=5778.0,
        )

        assert derived.planet_radius_rearth > 0
        assert derived.planet_radius_rjup > 0
        assert derived.semi_major_axis_au > 0
        assert 0 < derived.inclination_deg <= 90
        assert derived.equilibrium_temperature_k > 0
        assert derived.transit_depth_ppm > 0

    def test_limb_darkening_estimation(self):
        from astrotransit.modeling.parameters import TransitPriors

        # Güneş benzeri yıldız
        u1, u2 = TransitPriors._estimate_limb_darkening(5778.0)
        assert 0 < u1 < 1
        assert -1 < u2 < 1

        # Serin yıldız
        u1_cool, _ = TransitPriors._estimate_limb_darkening(3500.0)
        assert u1_cool > u1  # Serin yıldızlarda LD daha güçlü

    def test_kepler_third_law(self):
        from astrotransit.modeling.transit_model import TransitModel

        # Dünya: P ≈ 365.25d, a/Rs ≈ 215
        a_rs = TransitModel.compute_a_over_rs(
            period=365.25,
            stellar_mass=1.0,
            stellar_radius=1.0,
        )
        assert 210 < a_rs < 220


class TestTransitModel:
    """Transit model testleri."""

    def test_model_creates_dip(self):
        # TransitModel batman gerektirir; zarif degradasyon tasarımına göre
        # bağımlılık import edilemiyorsa bu test atlanır.
        pytest.importorskip(
            "batman",
            reason="batman-package bu ortamda import edilemiyor",
        )
        from astrotransit.modeling.transit_model import TransitModel, TransitModelParams

        time = np.linspace(0, 10, 10000)
        model = TransitModel(time)

        a_rs = TransitModel.compute_a_over_rs(3.5, 1.0, 1.0)

        params = TransitModelParams(
            period=3.5,
            t0=1.0,
            rp=0.1,
            a=a_rs,
            inc=87.0,
            u1=0.3,
            u2=0.2,
        )

        flux = model.flux(params)

        assert flux.min() < 1.0  # Transit çöküşü var
        assert abs(flux.max() - 1.0) < 1e-6  # Transit dışı ≈ 1.0
        assert len(flux) == len(time)

    def test_log_likelihood(self):
        # TransitModel batman gerektirir; zarif degradasyon tasarımına göre
        # bağımlılık import edilemiyorsa bu test atlanır.
        pytest.importorskip(
            "batman",
            reason="batman-package bu ortamda import edilemiyor",
        )
        from astrotransit.modeling.transit_model import TransitModel, TransitModelParams

        time = np.linspace(0, 10, 1000)
        model = TransitModel(time)

        a_rs = TransitModel.compute_a_over_rs(3.5, 1.0, 1.0)
        params = TransitModelParams(
            period=3.5, t0=1.0, rp=0.1, a=a_rs,
            inc=87.0, u1=0.3, u2=0.2,
        )

        model_flux = model.flux(params)
        flux_err = np.full(len(time), 1e-4)

        ll = model.log_likelihood(params, model_flux, flux_err)

        assert np.isfinite(ll)
        assert ll < 0  # Log-likelihood negatif olmalı