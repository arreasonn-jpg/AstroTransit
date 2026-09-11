"""Radius reliability policy tests."""

from astrotransit.modeling.reliability import assess_radius_reliability


def test_radius_boundary_has_highest_precedence() -> None:
    result = assess_radius_reliability(
        rp_rs=0.1,
        impact_parameter=0.95,
        optimizer_boundary_hits=("log_rp_rs:upper", "ld_q2:lower"),
    )
    assert result.status == "boundary_constrained"
    assert result.radius_at_optimizer_boundary is True
    assert result.is_grazing_geometry is True
    assert result.reasons == (
        "radius_optimizer_boundary",
        "grazing_transit_geometry",
    )


def test_grazing_geometry_uses_physical_contact_definition() -> None:
    full = assess_radius_reliability(rp_rs=0.1, impact_parameter=0.9)
    grazing = assess_radius_reliability(rp_rs=0.1, impact_parameter=0.900001)
    assert full.is_grazing_geometry is False
    assert grazing.status == "grazing_geometry"


def test_other_boundary_is_preserved_without_calling_radius_reliable() -> None:
    result = assess_radius_reliability(
        rp_rs=0.1,
        impact_parameter=0.3,
        optimizer_boundary_hits=("log_jitter:lower",),
    )
    assert result.status == "other_optimizer_boundary_contact"
    assert result.radius_at_optimizer_boundary is False


def test_unflagged_result_remains_explicitly_uncalibrated() -> None:
    result = assess_radius_reliability(rp_rs=0.1, impact_parameter=0.3)
    assert result.status == "uncalibrated_no_detected_flag"
    assert result.reasons == ()
