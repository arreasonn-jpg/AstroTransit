"""Evidence-gated scientific claim taxonomy.

The detector may discover a signal, but it must not silently promote that signal
into a confirmed planet.  This module is deliberately dependency-free so it can
be used by pipelines, exporters, and downstream audit scripts alike.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class ClaimStatus(StrEnum):
    DETECTED = "DETECTED"
    CANDIDATE = "CANDIDATE"
    MULTI_SECTOR_CONSISTENT = "MULTI_SECTOR_CONSISTENT"
    PHOTOMETRIC_PLANET_CANDIDATE = "PHOTOMETRIC_PLANET_CANDIDATE"
    EARTH_ANALOG_CANDIDATE = "EARTH_ANALOG_CANDIDATE"
    FOLLOWUP_SUPPORTED = "FOLLOWUP_SUPPORTED"
    VALIDATED_PLANET = "VALIDATED_PLANET"
    CONFIRMED_PLANET = "CONFIRMED_PLANET"


class ClaimEvidenceError(ValueError):
    """Raised when a result requests a claim unsupported by its evidence."""


def infer_claim_status(result: Mapping[str, Any] | Any) -> ClaimStatus:
    """Return the strongest claim supported by a result, never a stronger one.

    ``confirmed`` is intentionally ignored: only validated follow-up evidence
    can produce ``CONFIRMED_PLANET``.  A multi-sector label requires at least
    two sectors and an explicitly consistent result.
    """
    def get(name: str, default: Any = None) -> Any:
        return result.get(name, default) if isinstance(result, Mapping) else getattr(result, name, default)

    followup_confirmed = bool(get("followup_confirmed", False))
    followup_status = str(get("followup_status", ""))
    if followup_confirmed and followup_status == "followup_confirmed":
        return ClaimStatus.CONFIRMED_PLANET
    if followup_confirmed or followup_status == "followup_evidence_only":
        return ClaimStatus.FOLLOWUP_SUPPORTED

    n_sectors = get("n_sectors_evaluated", get("n_sectors", 0)) or 0
    consistent = get("sector_consistent", get("multi_sector_consistent", None))
    if int(n_sectors) >= 2 and consistent is True:
        return ClaimStatus.MULTI_SECTOR_CONSISTENT
    if bool(get("earth_analog", False)) or str(get("earth_analog_class", "")).strip():
        return ClaimStatus.EARTH_ANALOG_CANDIDATE
    if bool(get("detected", get("cascade_confirmed", False))):
        return ClaimStatus.PHOTOMETRIC_PLANET_CANDIDATE
    return ClaimStatus.DETECTED


def validate_claim(result: Mapping[str, Any] | Any, requested: str | ClaimStatus) -> ClaimStatus:
    """Validate an explicitly requested claim against available evidence."""
    requested_status = ClaimStatus(str(requested).upper())
    supported = infer_claim_status(result)
    order = list(ClaimStatus)
    if order.index(requested_status) > order.index(supported):
        raise ClaimEvidenceError(
            f"{requested_status.value} requires stronger evidence; "
            f"available claim is {supported.value}."
        )
    return requested_status


__all__ = ["ClaimEvidenceError", "ClaimStatus", "infer_claim_status", "validate_claim"]
