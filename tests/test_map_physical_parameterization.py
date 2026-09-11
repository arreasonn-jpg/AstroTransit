"""Physical quadratic limb-darkening and boundary-reporting tests."""

import numpy as np
import pytest

from astrotransit.modeling.parameterization import (
    is_physical_quadratic_limb_darkening,
    parameter_boundary_hits,
    quadratic_ld_to_unit_square,
    unit_square_to_quadratic_ld,
)


def test_kipping_transform_round_trip() -> None:
    for u1, u2 in [(0.3, 0.2), (0.6, 0.1), (0.2, -0.05), (0.0, 0.0)]:
        q1, q2 = quadratic_ld_to_unit_square(u1, u2)
        recovered_u1, recovered_u2 = unit_square_to_quadratic_ld(q1, q2)
        assert recovered_u1 == pytest.approx(u1)
        assert recovered_u2 == pytest.approx(u2)
        assert is_physical_quadratic_limb_darkening(recovered_u1, recovered_u2)


def test_unit_square_always_maps_to_physical_coefficients() -> None:
    for q1 in np.linspace(0.0, 1.0, 11):
        for q2 in np.linspace(0.0, 1.0, 11):
            u1, u2 = unit_square_to_quadratic_ld(q1, q2)
            assert is_physical_quadratic_limb_darkening(u1, u2)


def test_unphysical_coefficients_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unphysical"):
        quadratic_ld_to_unit_square(1.0, 1.0)
    with pytest.raises(ValueError, match="Unphysical"):
        quadratic_ld_to_unit_square(0.0, -0.5)


def test_parameter_boundary_hits_are_explicit_and_stable() -> None:
    hits = parameter_boundary_hits(
        [0.5, 0.25, 1.0],
        [(0.5, 2.0), (0.0, 1.0), (0.0, 1.0)],
        ["log_rp_rs", "ld_q1", "ld_q2"],
    )
    assert hits == ("log_rp_rs:lower", "ld_q2:upper")
