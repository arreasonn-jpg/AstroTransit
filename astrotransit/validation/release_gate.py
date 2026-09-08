"""Machine-readable release acceptance evaluation.

A gate is PASS only when its evidence exists. This module deliberately reports
PENDING rather than treating missing campaign data as a zero or a pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class GateResult:
    name: str
    required: str
    status: str
    observed: Any = None
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "required": self.required, "status": self.status,
                "observed": self.observed, "note": self.note}


@dataclass(frozen=True)
class ReleaseGateReport:
    release: str
    gates: tuple[GateResult, ...]

    @property
    def passed(self) -> bool:
        return bool(self.gates) and all(gate.status == "PASS" for gate in self.gates)

    def to_dict(self) -> dict[str, Any]:
        return {"release": self.release, "passed": self.passed,
                "gates": [gate.to_dict() for gate in self.gates]}


def evaluate_release_gates(
    *,
    known_targets: int,
    false_positives: int,
    quiet_controls: int,
    has_injection_report: bool = False,
    has_blind_report: bool = False,
    has_baseline_report: bool = False,
    has_provenance: bool = False,
    release: str = "v0.x-validation",
) -> ReleaseGateReport:
    checks = [
        _count_gate("known_planets", ">=50 labelled targets", known_targets, 50),
        _count_gate("false_positives", ">=100 labelled cases", false_positives, 100),
        _count_gate("quiet_controls", ">=100 negative controls", quiet_controls, 100),
        _bool_gate("injection_recovery", has_injection_report),
        _bool_gate("blind_test", has_blind_report),
        _bool_gate("independent_baseline", has_baseline_report),
        _bool_gate("provenance", has_provenance),
    ]
    return ReleaseGateReport(release, tuple(checks))


def _count_gate(name: str, required: str, observed: int, minimum: int) -> GateResult:
    status = "PASS" if observed >= minimum else "PENDING_DATA"
    return GateResult(name, required, status, observed,
                      "Evidence corpus is below release minimum." if status != "PASS" else "")


def _bool_gate(name: str, observed: bool) -> GateResult:
    return GateResult(name, "immutable report exists", "PASS" if observed else "PENDING_RUN", observed)


__all__ = ["GateResult", "ReleaseGateReport", "evaluate_release_gates"]
