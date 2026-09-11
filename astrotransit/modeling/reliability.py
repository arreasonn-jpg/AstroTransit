"""Evidence-preserving reliability labels for MAP radius estimates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class RadiusReliabilityAssessment:
    """Mechanical flags; no label implies calibrated scientific accuracy."""

    status: str
    reasons: tuple[str, ...]
    is_grazing_geometry: bool
    radius_at_optimizer_boundary: bool


def assess_radius_reliability(
    *,
    rp_rs: float,
    impact_parameter: float,
    optimizer_boundary_hits: Iterable[str] = (),
) -> RadiusReliabilityAssessment:
    """Classify directly observable identifiability warnings without thresholds."""

    hits = tuple(str(item) for item in optimizer_boundary_hits)
    radius_at_boundary = any(item.startswith("log_rp_rs:") for item in hits)
    # A full transit requires b <= 1 - Rp/Rs. The remaining transiting geometry is grazing.
    is_grazing = float(impact_parameter) > 1.0 - float(rp_rs)
    other_boundary = bool(hits) and not radius_at_boundary

    reasons: list[str] = []
    if radius_at_boundary:
        reasons.append("radius_optimizer_boundary")
    if is_grazing:
        reasons.append("grazing_transit_geometry")
    if other_boundary:
        reasons.append("other_optimizer_boundary_contact")

    if radius_at_boundary:
        status = "boundary_constrained"
    elif is_grazing:
        status = "grazing_geometry"
    elif other_boundary:
        status = "other_optimizer_boundary_contact"
    else:
        status = "uncalibrated_no_detected_flag"

    return RadiusReliabilityAssessment(
        status=status,
        reasons=tuple(reasons),
        is_grazing_geometry=is_grazing,
        radius_at_optimizer_boundary=radius_at_boundary,
    )
