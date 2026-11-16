"""Machine-readable release acceptance evaluation.

A gate is PASS only when its evidence exists. This module deliberately reports
PENDING rather than treating missing campaign data as a zero or a pass.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    has_robustness_report: bool = False,
    has_provenance: bool = False,
    l1_pool: Any = None,
    release: str = "v0.x-validation",
) -> ReleaseGateReport:
    checks = [
        _count_gate("known_planets", ">=50 labelled targets", known_targets, 50),
        _count_gate("false_positives", ">=100 labelled cases", false_positives, 100),
        _count_gate("quiet_controls", ">=100 negative controls", quiet_controls, 100),
        _bool_gate("injection_recovery", has_injection_report),
        _bool_gate("blind_test", has_blind_report),
        _bool_gate("independent_baseline", has_baseline_report),
        _bool_gate("cadence_robustness", has_robustness_report),
        _bool_gate("provenance", has_provenance),
        _l1_claim_gate(l1_pool),
    ]
    return ReleaseGateReport(release, tuple(checks))


def _l1_claim_gate(l1_pool: Any) -> GateResult:
    """L1 havuzu varsa claim-firewall tutarlılığını kontrol eder.

    Havuz yoksa gate ``PENDING_RUN`` olur (veri yok = pass değil).
    Havuz varsa her kaydın ``l1_claim_label`` değeri ``infer_l1_claim`` ile
    yeniden türetilir; uyuşmazlık varsa gate FAIL olur. "L1'de görüldü"
    kontrol kanıtı olamayacağından ``L1_CONTROLLED_STRUCTURE_CANDIDATE``
    ancak review skoru + bütçe birlikte varsa kabul edilir.
    """

    if l1_pool is None:
        return GateResult(
            "l1_claim_firewall",
            "L1 havuzu claim etiketleriyle tutarlı",
            "PENDING_RUN",
            None,
            "L1 havuzu verilmedi.",
        )
    from astrotransit.validation.l1_claims import infer_l1_claim

    entries = l1_pool.get("targets", []) if isinstance(l1_pool, dict) else list(l1_pool)
    mismatches = 0
    for entry in entries:
        record = entry if isinstance(entry, dict) else getattr(entry, "to_dict", lambda: {})()
        if not record.get("l1_assessed"):
            continue
        # Havuz kaydı kol sonuçlarını iç içe taşıyorsa bunları düz alana çıkar.
        flat = dict(record)
        structure = record.get("l1_structure") or {}
        earth = record.get("l1_earth_twin") or {}
        flat.setdefault("l1_stationkeeping_review_score", structure.get("stationkeeping_review_score"))
        budget_dv = structure.get("station_keeping_total_delta_v_m_per_s")
        flat.setdefault(
            "station_keeping_budget_ok",
            budget_dv is not None and float(budget_dv) <= 100.0,
        )
        flat.setdefault("host_in_habitable_zone", earth.get("host_in_habitable_zone"))
        flat.setdefault("l1_insolation_in_habitable_range", earth.get("eligible"))
        flat.setdefault("earth_similarity_score", earth.get("earth_similarity_score"))
        expected = infer_l1_claim(flat).value
        if record.get("l1_claim_label") != expected:
            mismatches += 1
    if mismatches:
        return GateResult(
            "l1_claim_firewall",
            "L1 havuzu claim etiketleriyle tutarlı",
            "FAIL",
            mismatches,
            f"{mismatches} kayıtta l1_claim_label infer_l1_claim ile uyuşmuyor.",
        )
    return GateResult(
        "l1_claim_firewall",
        "L1 havuzu claim etiketleriyle tutarlı",
        "PASS",
        len(entries),
        "Tüm L1 etiketleri kanıtla türetildi.",
    )


def _count_gate(name: str, required: str, observed: int, minimum: int) -> GateResult:
    status = "PASS" if observed >= minimum else "PENDING_DATA"
    return GateResult(name, required, status, observed,
                      "Evidence corpus is below release minimum." if status != "PASS" else "")


def _bool_gate(name: str, observed: bool) -> GateResult:
    return GateResult(name, "immutable report exists", "PASS" if observed else "PENDING_RUN", observed)


__all__ = ["GateResult", "ReleaseGateReport", "evaluate_release_gates"]
