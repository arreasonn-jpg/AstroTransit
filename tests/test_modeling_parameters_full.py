"""astrotransit/modeling/parameters.py için kapsamlı testler."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from astrotransit.modeling.parameters import (
    CONST,
    TRANSIT_PARAMETER_BOUNDS,
    DerivedParameters,
    ParameterBounds,
    PhysicalConstants,
    TransitPriors,
    compute_derived_parameters,
)

# ═══════════════════════════════════════════════════════
# PhysicalConstants
# ═══════════════════════════════════════════════════════

def test_physical_constants_values():
    assert pytest.approx(6.674e-11) == CONST.G
    assert pytest.approx(6.957e8) == CONST.R_SUN
    assert pytest.approx(1.989e30) == CONST.M_SUN
    assert pytest.approx(7.1492e7) == CONST.R_JUP
    assert pytest.approx(6.371e6) == CONST.R_EARTH
    assert pytest.approx(1.496e11) == CONST.AU
    assert CONST.T_SUN == 5778.0


def test_const_instance():
    c = PhysicalConstants()
    assert c.G == CONST.G


# ═══════════════════════════════════════════════════════
# ParameterBounds
# ═══════════════════════════════════════════════════════

def test_bounds_is_valid_in_range():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.is_valid(0.5) is True


def test_bounds_is_valid_at_boundaries():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.is_valid(0.0) is True
    assert b.is_valid(1.0) is True


def test_bounds_is_valid_outside():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.is_valid(-0.1) is False
    assert b.is_valid(1.1) is False


def test_bounds_clip_above():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.clip(2.0) == 1.0


def test_bounds_clip_below():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.clip(-1.0) == 0.0


def test_bounds_clip_in_range():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.clip(0.5) == 0.5


def test_bounds_prior_defaults():
    b = ParameterBounds("x", 0.0, 1.0, "u", "desc")
    assert b.prior_type == "uniform"
    assert b.prior_mu is None
    assert b.prior_sigma is None


# ═══════════════════════════════════════════════════════
# TRANSIT_PARAMETER_BOUNDS
# ═══════════════════════════════════════════════════════

def test_transit_bounds_contains_all():
    for key in ("period", "t0", "rp_rs", "duration", "impact_parameter",
                "stellar_radius", "stellar_mass", "stellar_density",
                "u1", "u2", "log_jitter", "baseline"):
        assert key in TRANSIT_PARAMETER_BOUNDS


def test_transit_bounds_prior_types():
    assert TRANSIT_PARAMETER_BOUNDS["period"].prior_type == "uniform"
    assert TRANSIT_PARAMETER_BOUNDS["stellar_radius"].prior_type == "normal"
    assert TRANSIT_PARAMETER_BOUNDS["stellar_density"].prior_type == "loguniform"


# ═══════════════════════════════════════════════════════
# TransitPriors
# ═══════════════════════════════════════════════════════

def test_priors_defaults():
    p = TransitPriors()
    assert p.period == 1.0
    assert p.rp_rs == 0.1
    assert p.u1 == 0.3
    assert p.u2 == 0.2
    assert p.baseline == 1.0


def test_priors_to_dict():
    p = TransitPriors()
    d = p.to_dict()
    assert d["period"] == 1.0
    assert d["t0"] == 0.0
    assert d["u1"] == 0.3
    assert d["stellar_radius"] == 1.0


def _make_candidate(
    period=3.5, period_err=0.01, t0=100.0, rp_rs=0.1, duration=0.1,
):
    return SimpleNamespace(
        period=period, period_err=period_err, t0=t0,
        rp_rs=rp_rs, duration=duration,
    )


def test_priors_from_cascade_basic():
    p = TransitPriors.from_cascade(_make_candidate())
    assert p.period == 3.5
    assert p.t0 == 100.0
    assert p.rp_rs == 0.1
    assert p.duration == 0.1


def test_priors_from_cascade_period_bounds():
    p = TransitPriors.from_cascade(_make_candidate(period=3.5, period_err=0.01))
    # period_err=0.01, 5*0.01 = 0.05
    assert p.period_bounds == (pytest.approx(3.45), pytest.approx(3.55))


def test_priors_from_cascade_period_err_fallback():
    # period_err < period * 0.001 ise period*0.001 kullanılır
    p = TransitPriors.from_cascade(_make_candidate(period=100.0, period_err=0.0))
    # period * 0.001 = 0.1; 5 * 0.1 = 0.5
    assert p.period_bounds == (pytest.approx(99.5), pytest.approx(100.5))


def test_priors_from_cascade_t0_bounds():
    p = TransitPriors.from_cascade(_make_candidate(period=3.5, t0=100.0))
    assert p.t0_bounds == (pytest.approx(96.5), pytest.approx(103.5))


def test_priors_from_cascade_rp_rs_bounds():
    p = TransitPriors.from_cascade(_make_candidate(rp_rs=0.1))
    assert p.rp_rs_bounds == (pytest.approx(0.05), pytest.approx(0.2))


def test_priors_from_cascade_rp_rs_min():
    # rp_rs negatif → max(0.001, ...) = 0.001
    p = TransitPriors.from_cascade(_make_candidate(rp_rs=-1.0))
    assert p.rp_rs == 0.001


def test_priors_from_cascade_rp_rs_upper_clip():
    # rp_rs büyük → hi = min(0.5, 2*rp_rs) = 0.5
    p = TransitPriors.from_cascade(_make_candidate(rp_rs=0.4))
    assert p.rp_rs_bounds[1] == 0.5


def test_priors_from_cascade_duration_bounds():
    p = TransitPriors.from_cascade(_make_candidate(duration=0.1))
    # (0.05, 0.2)
    assert p.duration_bounds == (pytest.approx(0.05), pytest.approx(0.2))


def test_priors_from_cascade_duration_min():
    p = TransitPriors.from_cascade(_make_candidate(duration=0.001))
    # max(0.005, 0.0005) = 0.005
    assert p.duration_bounds[0] == 0.005


def test_priors_from_cascade_duration_max_clip():
    p = TransitPriors.from_cascade(_make_candidate(duration=0.8))
    # min(1.0, 1.6) = 1.0
    assert p.duration_bounds[1] == 1.0


def test_priors_from_cascade_stellar_passthrough():
    p = TransitPriors.from_cascade(
        _make_candidate(), stellar_radius=1.5, stellar_mass=1.2, stellar_teff=6000.0,
    )
    assert p.stellar_radius == 1.5
    assert p.stellar_mass == 1.2
    assert p.stellar_teff == 6000.0


# ═══════════════════════════════════════════════════════
# _estimate_limb_darkening
# ═══════════════════════════════════════════════════════

def test_limb_darkening_sun_like():
    u1, u2 = TransitPriors._estimate_limb_darkening(5778.0)
    assert 0.2 < u1 < 0.5
    assert 0.15 < u2 < 0.25


def test_limb_darkening_cool_star():
    u1_cool, _ = TransitPriors._estimate_limb_darkening(3500.0)
    u1_hot, _ = TransitPriors._estimate_limb_darkening(7000.0)
    # Serin yıldızlar daha yüksek u1
    assert u1_cool > u1_hot


def test_limb_darkening_below_grid():
    # teff < 3500 → clip → grid[0]
    u1, u2 = TransitPriors._estimate_limb_darkening(2000.0)
    assert u1 == pytest.approx(0.60)
    assert u2 == pytest.approx(0.15)


def test_limb_darkening_above_grid():
    # teff > 7000 → clip → grid[-1]
    u1, u2 = TransitPriors._estimate_limb_darkening(10000.0)
    assert u1 == pytest.approx(0.22)
    assert u2 == pytest.approx(0.18)


def test_limb_darkening_midpoint():
    # teff = 5000 → u1 = 0.40, u2 = 0.19
    u1, u2 = TransitPriors._estimate_limb_darkening(5000.0)
    assert u1 == pytest.approx(0.40)
    assert u2 == pytest.approx(0.19)


# ═══════════════════════════════════════════════════════
# DerivedParameters
# ═══════════════════════════════════════════════════════

def test_derived_defaults():
    d = DerivedParameters()
    assert d.planet_radius_rjup == 0.0
    assert d.inclination_deg == 90.0
    assert d.equilibrium_temperature_albedo == 0.3


def test_derived_to_dict():
    d = DerivedParameters(
        planet_radius_rjup=0.1, planet_radius_rearth=1.12,
        semi_major_axis_au=0.05, inclination_deg=88.5,
        stellar_density_gcm3=1.4, equilibrium_temperature_k=280.0,
        transit_depth_ppm=1000.0, insolation_flux=1.2,
    )
    out = d.to_dict()
    assert out["planet_radius_rjup"] == 0.1
    assert out["transit_depth_ppm"] == 1000.0
    assert out["equilibrium_temperature_albedo"] == 0.3


# ═══════════════════════════════════════════════════════
# compute_derived_parameters
# ═══════════════════════════════════════════════════════

def _earth_params(**over):
    base = dict(
        period=365.25, rp_rs=0.00916, impact_parameter=0.0,
        duration=0.5, stellar_radius=1.0, stellar_mass=1.0,
        stellar_teff=5778.0,
    )
    base.update(over)
    return base


def test_compute_earth_like():
    d = compute_derived_parameters(**_earth_params())
    # Dünya yarıçapı ~1 R_earth (rp_rs = 0.00916 → 0.00916 * R_SUN / R_EARTH)
    assert 0.95 < d.planet_radius_rearth < 1.05
    assert d.planet_radius_rjup > 0
    assert d.transit_depth_ppm == pytest.approx(0.00916**2 * 1e6, rel=1e-3)
    assert d.semi_major_axis_au == pytest.approx(1.0, abs=0.01)
    assert d.inclination_deg == pytest.approx(90.0, abs=0.5)
    assert d.equilibrium_temperature_k > 200.0
    assert d.insolation_flux == pytest.approx(1.0, rel=0.05)


def test_compute_hot_jupiter():
    d = compute_derived_parameters(
        period=3.5, rp_rs=0.1, impact_parameter=0.3,
        duration=0.1, stellar_radius=1.0, stellar_mass=1.0, stellar_teff=5778.0,
    )
    # rp_rs=0.1 → R_p ≈ 0.1 * R_SUN / R_JUP ≈ 0.97 R_JUP
    assert 0.9 < d.planet_radius_rjup < 1.05
    assert d.planet_radius_rearth > 10.0
    assert d.semi_major_axis_au < 0.1


def test_compute_albedo_invalid_high():
    with pytest.raises(ValueError, match="albedo"):
        compute_derived_parameters(**_earth_params(), albedo=1.5)


def test_compute_albedo_invalid_low():
    with pytest.raises(ValueError, match="albedo"):
        compute_derived_parameters(**_earth_params(), albedo=-0.1)


def test_compute_albedo_nan():
    with pytest.raises(ValueError, match="albedo"):
        compute_derived_parameters(**_earth_params(), albedo=float("nan"))


def test_compute_albedo_zero():
    d = compute_derived_parameters(**_earth_params(), albedo=0.0)
    assert d.equilibrium_temperature_albedo == 0.0
    # Albedo=0 → daha yüksek T_eq
    d03 = compute_derived_parameters(**_earth_params(), albedo=0.3)
    assert d.equilibrium_temperature_k > d03.equilibrium_temperature_k


def test_compute_zero_period_semi_major_zero():
    """P=0 → a = 0."""
    d = compute_derived_parameters(
        period=0.0, rp_rs=0.1, impact_parameter=0.0, duration=0.1,
        stellar_radius=1.0, stellar_mass=1.0, stellar_teff=5778.0,
    )
    # a = 0 → derived bazı alanlar 0 olabilir
    assert d.semi_major_axis_au == 0.0


def test_compute_zero_stellar_radius():
    """Rs=0 → yoğunluk ve yörünge hesapları etkilenir."""
    d = compute_derived_parameters(
        period=3.5, rp_rs=0.1, impact_parameter=0.3, duration=0.1,
        stellar_radius=0.0, stellar_mass=1.0, stellar_teff=5778.0,
    )
    # planet_radius 0
    assert d.planet_radius_rjup == 0.0
    # semi_major_axis pozitif (Kepler ile)
    assert d.semi_major_axis_au > 0


def test_compute_zero_teff():
    d = compute_derived_parameters(
        period=3.5, rp_rs=0.1, impact_parameter=0.3, duration=0.1,
        stellar_radius=1.0, stellar_mass=1.0, stellar_teff=0.0,
    )
    # T_eq = 0 (stellar_teff=0)
    assert d.equilibrium_temperature_k == 0.0


def test_compute_impact_parameter_clipped():
    """b > a/Rs ise cos_i clip'lenir (inclination 0 veya 180)."""
    d = compute_derived_parameters(
        period=3.5, rp_rs=0.1, impact_parameter=10.0, duration=0.1,
        stellar_radius=1.0, stellar_mass=1.0, stellar_teff=5778.0,
    )
    # cos_i = 10 * R_SUN / a_m, muhtemelen > 1 → clip → arccos(1) = 0
    assert 0.0 <= d.inclination_deg <= 180.0


def test_compute_negative_period():
    d = compute_derived_parameters(
        period=-1.0, rp_rs=0.1, impact_parameter=0.0, duration=0.1,
        stellar_radius=1.0, stellar_mass=1.0, stellar_teff=5778.0,
    )
    # period_s negatif → period_s**2 pozitif, a_m hesaplanır
    assert d.semi_major_axis_au > 0


def test_compute_low_mass():
    d = compute_derived_parameters(
        period=3.5, rp_rs=0.1, impact_parameter=0.3, duration=0.1,
        stellar_radius=1.0, stellar_mass=0.1, stellar_teff=3500.0,
    )
    assert d.semi_major_axis_au > 0
    assert d.equilibrium_temperature_k > 0


def test_compute_massive_star():
    # rp_rs=0.05, Rs=10 R_sun → R_p = 0.5 R_sun = 0.5*6.957e8/6.371e6 ≈ 54.6 R_earth
    d = compute_derived_parameters(
        period=100.0, rp_rs=0.05, impact_parameter=0.1, duration=0.3,
        stellar_radius=10.0, stellar_mass=20.0, stellar_teff=20000.0,
    )
    assert d.semi_major_axis_au > 0
    assert d.planet_radius_rearth == pytest.approx(54.6, abs=1.0)


def test_compute_from_cascade_to_derived_integration():
    """from_cascade → compute_derived_parameters zinciri."""
    p = TransitPriors.from_cascade(_make_candidate())
    d = compute_derived_parameters(
        period=p.period, rp_rs=p.rp_rs,
        impact_parameter=p.impact_parameter, duration=p.duration,
        stellar_radius=p.stellar_radius, stellar_mass=p.stellar_mass,
        stellar_teff=p.stellar_teff,
    )
    assert d.planet_radius_rearth > 0
    assert d.semi_major_axis_au > 0
