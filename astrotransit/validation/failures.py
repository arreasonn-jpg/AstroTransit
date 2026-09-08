"""Structured failure taxonomy for pipeline and validation reports."""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Mapping


class FailureCode(StrEnum):
    NO_DATA = "NO_DATA"
    INSUFFICIENT_BASELINE = "INSUFFICIENT_BASELINE"
    HIGH_SYSTEMATICS = "HIGH_SYSTEMATICS"
    NO_TRANSIT = "NO_TRANSIT"
    AMBIGUOUS_SINGLE_TRANSIT = "AMBIGUOUS_SINGLE_TRANSIT"
    MULTI_SECTOR_INCONSISTENT = "MULTI_SECTOR_INCONSISTENT"
    MODEL_NONCONVERGENCE = "MODEL_NONCONVERGENCE"
    MCMC_DIAGNOSTIC_FAILURE = "MCMC_DIAGNOSTIC_FAILURE"
    FPP_UNCALIBRATED = "FPP_UNCALIBRATED"
    MISSING_STELLAR_PARAMETERS = "MISSING_STELLAR_PARAMETERS"


def classify_failure(result: Mapping[str, Any] | Any) -> tuple[FailureCode, ...]:
    """Derive explicit failure codes without collapsing unknown into false."""
    def get(name: str, default: Any = None) -> Any:
        return result.get(name, default) if isinstance(result, Mapping) else getattr(result, name, default)

    codes: list[FailureCode] = []
    if get("no_data", False) or get("n_points", None) == 0:
        codes.append(FailureCode.NO_DATA)
    if get("insufficient_baseline", False):
        codes.append(FailureCode.INSUFFICIENT_BASELINE)
    if get("high_systematics", False):
        codes.append(FailureCode.HIGH_SYSTEMATICS)
    if get("no_transit", False) or (get("detected", None) is False and not codes):
        codes.append(FailureCode.NO_TRANSIT)
    if get("ambiguous_single_transit", False):
        codes.append(FailureCode.AMBIGUOUS_SINGLE_TRANSIT)
    if get("claim_status") == "multi_sector_inconsistent" or get("multi_sector_inconsistent", False):
        codes.append(FailureCode.MULTI_SECTOR_INCONSISTENT)
    if get("fit_status") in {"failed", "nonconverged"} or get("model_nonconverged", False):
        codes.append(FailureCode.MODEL_NONCONVERGENCE)
    if get("mcmc_quality") == "MCMC_FAILED_DIAGNOSTICS" or get("mcmc_diagnostic_failure", False):
        codes.append(FailureCode.MCMC_DIAGNOSTIC_FAILURE)
    if get("fpp_method") in {"", "unknown", "heuristic_uncalibrated"} and get("fpp", None) is not None:
        codes.append(FailureCode.FPP_UNCALIBRATED)
    if any(get(name, None) is None for name in ("radius_rsun", "teff_k")):
        codes.append(FailureCode.MISSING_STELLAR_PARAMETERS)
    return tuple(dict.fromkeys(codes))


def failure_codes_as_json(result: Mapping[str, Any] | Any) -> str:
    import json
    return json.dumps([code.value for code in classify_failure(result)])


__all__ = ["FailureCode", "classify_failure", "failure_codes_as_json"]
