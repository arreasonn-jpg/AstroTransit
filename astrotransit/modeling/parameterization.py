"""Physical parameterizations and optimizer-boundary diagnostics."""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

LIMB_DARKENING_PARAMETERIZATION = "kipping_q1_q2"


def is_physical_quadratic_limb_darkening(
    u1: float,
    u2: float,
    *,
    tolerance: float = 1e-12,
) -> bool:
    """Return whether quadratic coefficients lie in the physical Kipping region."""

    if not math.isfinite(u1) or not math.isfinite(u2):
        return False
    total = u1 + u2
    return (
        u1 >= -tolerance
        and total >= -tolerance
        and total <= 1.0 + tolerance
        and u1 + 2.0 * u2 >= -tolerance
    )


def quadratic_ld_to_unit_square(u1: float, u2: float) -> tuple[float, float]:
    """Transform physical quadratic coefficients to Kipping (q1, q2)."""

    u1 = float(u1)
    u2 = float(u2)
    if not is_physical_quadratic_limb_darkening(u1, u2):
        raise ValueError(f"Unphysical quadratic limb darkening: u1={u1}, u2={u2}")
    total = u1 + u2
    if total <= 0.0:
        return 0.0, 0.5
    q1 = total * total
    q2 = u1 / (2.0 * total)
    return float(np.clip(q1, 0.0, 1.0)), float(np.clip(q2, 0.0, 1.0))


def unit_square_to_quadratic_ld(q1: float, q2: float) -> tuple[float, float]:
    """Transform Kipping (q1, q2) coordinates to physical coefficients."""

    q1 = float(q1)
    q2 = float(q2)
    if not math.isfinite(q1) or not math.isfinite(q2):
        raise ValueError("Limb-darkening unit-square coordinates must be finite")
    if not 0.0 <= q1 <= 1.0 or not 0.0 <= q2 <= 1.0:
        raise ValueError(f"Limb-darkening coordinates outside [0, 1]: q1={q1}, q2={q2}")
    root = math.sqrt(q1)
    u1 = 2.0 * root * q2
    u2 = root * (1.0 - 2.0 * q2)
    return u1, u2


def parameter_boundary_hits(
    values: Sequence[float],
    bounds: Sequence[tuple[float | None, float | None]],
    names: Sequence[str],
    *,
    relative_tolerance: float = 1e-5,
    absolute_tolerance: float = 1e-8,
) -> tuple[str, ...]:
    """Return stable ``name:lower|upper`` labels for optimizer-bound contacts."""

    if not (len(values) == len(bounds) == len(names)):
        raise ValueError("values, bounds, and names must have equal lengths")
    hits: list[str] = []
    for value, (lower, upper), name in zip(values, bounds, names):
        value = float(value)
        if lower is not None and np.isclose(
            value, lower, rtol=relative_tolerance, atol=absolute_tolerance
        ):
            hits.append(f"{name}:lower")
        if upper is not None and np.isclose(
            value, upper, rtol=relative_tolerance, atol=absolute_tolerance
        ):
            hits.append(f"{name}:upper")
    return tuple(hits)
