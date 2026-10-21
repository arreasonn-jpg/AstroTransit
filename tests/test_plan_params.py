"""plan_params (Analiz Parametreleri) birim testleri — saf mantık."""


from __future__ import annotations

import math

import pytest

from astrotransit.pipelines.plan_params import (
    R_EARTH_CM,
    R_SUN_CM,
    PlanParams,
    build_plan_priors,
    impact_parameter_from_geometry,
    plan_params_from_user_input,
    rp_rs_from_planet_radius_rearth,
    stellar_radius_from_log_l,
)


def _full_values(**overrides: object) -> dict[str, object]:
    """Geçerli örnek girdi (Periyot + T0 zorunlu ikili dolu)."""

    base: dict[str, object] = {
        "period_days": 3.5,
        "t0_btjd": 2450.0,
    }
    base.update(overrides)
    return base


class TestPlanParamsFromUserInput:
    def test_all_blank_returns_none(self):
        assert plan_params_from_user_input(None) is None
        assert (
            plan_params_from_user_input({k: "" for k in (
                "period_days", "t0_btjd", "rp_rs", "impact_parameter",
                "a_over_rs", "inclination_deg", "planet_radius_rearth",
                "planet_radius_rjup", "semi_major_axis_au", "teff_k", "log_l_lsun",
            )})
            is None
        )

    def test_partial_values_accepted(self):
        params = plan_params_from_user_input(
            {"period_days": "3.5", "t0_btjd": "2450", "rp_rs": ""}
        )
        assert params is not None
        assert params.period_days == pytest.approx(3.5)
        assert params.t0_btjd == pytest.approx(2450.0)
        assert params.rp_rs is None

    def test_invalid_number_raises_with_field(self):
        with pytest.raises(ValueError, match="period_days"):
            plan_params_from_user_input({"period_days": "abc", "t0_btjd": "1"})

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match="Rp/Rs"):
            plan_params_from_user_input(_full_values(rp_rs=0.9))

    def test_incomplete_for_plan_mode(self):
        params = plan_params_from_user_input({"period_days": "3.5"})
        assert params is not None
        assert not params.complete_for_plan_mode()
        assert params.t0_btjd is None


class TestStellarRadius:
    def test_sun_like_identity(self):
        assert stellar_radius_from_log_l(5778.0, 0.0) == pytest.approx(1.0)

    def test_ten_luminosities(self):
        assert stellar_radius_from_log_l(5778.0, 1.0) == pytest.approx(
            math.sqrt(10.0)
        )

    def test_cooler_rendered_larger(self):
        assert stellar_radius_from_log_l(3000.0, 0.0) > 2.0


class TestGeometry:
    def test_b_from_geometry_edge_on(self):
        b = impact_parameter_from_geometry(10.0, 90.0)
        assert b == pytest.approx(0.0, abs=1e-9)

    def test_b_from_geometry_inclined(self):
        b = impact_parameter_from_geometry(10.0, 60.0)
        assert b == pytest.approx(5.0)

    def test_invalid_inclination(self):
        with pytest.raises(ValueError, match="0-90"):
            impact_parameter_from_geometry(10.0, 95.0)


class TestRpRs:
    def test_one_earth_radius_star_sun_radius(self):
        assert rp_rs_from_planet_radius_rearth(1.0, 1.0) == pytest.approx(
            R_EARTH_CM / R_SUN_CM
        )


class TestBuildPlanPriors:
    def test_missing_required_raises(self):
        plan = PlanParams(period_days=3.5)
        with pytest.raises(ValueError, match="Periyot ve T0"):
            build_plan_priors(
                plan, stellar_radius=1.0, stellar_mass=1.0, stellar_teff=5778.0
            )

    def test_full_flow(self):
        plan = plan_params_from_user_input(
            _full_values(
                planet_radius_rearth=1.0,
                teff_k=5778.0,
                log_l_lsun=0.0,
                a_over_rs=10.0,
                inclination_deg=88.0,
            )
        )
        assert plan is not None
        priors = build_plan_priors(
            plan, stellar_radius=1.5, stellar_mass=1.0, stellar_teff=5000.0
        )
        # yıldız: formül T=5778 + logL=0 → R★=1 (katalog 1.5'e üstün)
        assert priors.stellar_radius == pytest.approx(1.0)
        assert priors.stellar_teff == pytest.approx(5778.0)
        # Rp/Rs Re'den
        assert priors.rp_rs == pytest.approx(R_EARTH_CM / R_SUN_CM, rel=1e-6)
        # b geometriden: 10·cos(88°)
        assert priors.impact_parameter == pytest.approx(10.0 * math.cos(math.radians(88.0)))
        # sık periyot penceresi ±%2
        assert priors.period_bounds[0] == pytest.approx(3.5 * 0.98)
        assert priors.period_bounds[1] == pytest.approx(3.5 * 1.02)
        # t0 penceresi ±0.25 d
        assert priors.t0_bounds[0] == pytest.approx(2450.0 - 0.25)
        assert priors.t0_bounds[1] == pytest.approx(2450.0 + 0.25)

    def test_direct_impact_overrides_geometry(self):
        values = _full_values(
            impact_parameter=0.3, a_over_rs=10.0, inclination_deg=60.0
        )
        plan = plan_params_from_user_input(values)
        assert plan is not None
        priors = build_plan_priors(
            plan, stellar_radius=1.0, stellar_mass=1.0, stellar_teff=5778.0
        )
        assert priors.impact_parameter == pytest.approx(0.3)
