"""Sentetik adversarial false-positive corpus'u ve sonuç sınıflandırması.

Bu modül, vetting zincirinin **bilinen gezegen-olmayan morfolojileri** ne
oranında elediğini ölçmek için deterministik sentetik ışık eğrileri üretir.
Amaç gerçek TESS sistematiğini taklit etmek değil, vetting testlerinin her
birini **niyet edilmiş tetikleyicisiyle** karşı karşıya getirmektir; bu
nedenle her ailenin hangi testi hedeflediği tabloda belgelenir.

Sözleşme:

- Şekiller ``batman`` gerektirmez (opsiyonel bağımlılık); trapez/V modeli
  analitiktir: ``steepness -> 0`` kutu, ``steepness = 1`` üçgen (V).
- Karantina amaçlı **pozitif kontrol** ailesi (`planetary_control`) vardır.
  Salt "her şeyi reddet" ayarı metriği geçemez: kontrol kabul oranı da
  raporda zorunlu bir koşuldur.
- Hiçbir oran hata satırlarının üzerinden hesaplanmaz; değerlendirilemeyen
  senaryo `error` olarak sayılır ve kapıyı kapatır.
- Sentetik ölçüm gerçek bir EPİC/TESS gözlemi değildir: iddia sınırı
  raporda `claim_boundary` olarak taşınır.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import numpy as np

#: Gözlem tasarımının dondurulmuş parametreleri (korpus özeti bunları taşır).
BASELINE_DAYS = 27.0
CADENCE_DAYS = 600.0 / 86400.0  # 600 s örneklenme
N_POINTS = int(round(BASELINE_DAYS / CADENCE_DAYS))  # 3888 nokta
NOISE_PPM = 600.0

#: Vetting/FPP karar eşiği (heuristik proxy için ilan edilmiş red eşiği).
ADVERSARIAL_FPP_REJECT_THRESHOLD = 0.5

REJECTION_OUTCOMES = (
    "rejected_at_detection",
    "rejected_at_cascade",
    "rejected_at_vetting",
    "rejected_at_anomaly",
)
ANOMALY_REJECT_FLAG = "REJECT"
LEAK_OUTCOME = "leaked_as_candidate"

#: Aile → hedeflenen vetting testi. Yeni aile eklerken burası güncellenir.
ADVERSARIAL_FAMILIES: dict[str, dict[str, str]] = {
    "eclipsing_binary_v": {
        "shape": "V-shaped, deep",
        "targets_test": "depth_limit, secondary_eclipse",
        "expected": "false_positive",
    },
    "grazing_eclipsing_binary": {
        "shape": "V-shaped, shallow, no secondary",
        "targets_test": "depth_variance, odd_even",
        "expected": "false_positive",
    },
    "blended_diluted_eb": {
        "shape": "V-shaped diluted to planet-scale depth",
        "targets_test": "shape/variance only (hardest family)",
        "expected": "false_positive",
    },
    "eb_with_secondary_eclipse": {
        "shape": "primary + asymmetric secondary at phase 0.5",
        "targets_test": "secondary_eclipse",
        "expected": "false_positive",
    },
    "odd_even_alternating_eb": {
        "shape": "alternating eclipse depths",
        "targets_test": "odd_even",
        "expected": "false_positive",
    },
    "spot_modulated_dip": {
        "shape": "sinusoidal variability + narrow dip",
        "targets_test": "stellar_variability, depth_variance",
        "expected": "false_positive",
    },
    "planetary_control": {
        "shape": "boxy, planet-scale, no secondary",
        "targets_test": "positive control (must mostly be ACCEPTED)",
        "expected": "planet",
    },
}


@dataclass(frozen=True)
class AdversarialScenario:
    """Tek bir sentetik adversarial senaryo tanımı."""

    family: str
    index: int
    seed: int
    period_days: float
    depth: float
    duration_days: float
    t0_days: float = 0.0
    steepness: float = 1.0
    dilution: float = 1.0
    secondary_fraction: float = 0.0
    alternate_ratio: float = 1.0
    variability_amplitude: float = 0.0
    variability_period_days: float = 0.0
    noise_ppm: float = NOISE_PPM

    @property
    def scenario_id(self) -> str:
        return f"{self.family}:{self.index:03d}"

    @property
    def expected(self) -> str:
        return ADVERSARIAL_FAMILIES[self.family]["expected"]

    def validate(self) -> None:
        if self.family not in ADVERSARIAL_FAMILIES:
            raise ValueError(f"bilinmeyen adversarial aile: {self.family}")
        if not 0.0 < self.depth <= 0.5:
            raise ValueError(f"{self.scenario_id}: depth (0, 0.5] aralığında olmalı")
        if not 0.05 < self.period_days <= 12.0:
            raise ValueError(f"{self.scenario_id}: period_days 0.05-12 gün aralığında olmalı")
        if not 0.0 < self.duration_days < 0.5 * self.period_days:
            raise ValueError(f"{self.scenario_id}: duration, periyodun yarısından küçük olmalı")
        if not 0.0 < self.steepness <= 1.0:
            raise ValueError(f"{self.scenario_id}: steepness (0, 1] aralığında olmalı")
        if not 0.0 < self.dilution <= 1.0:
            raise ValueError(f"{self.scenario_id}: dilution (0, 1] aralığında olmalı")
        if not 0.0 <= self.secondary_fraction < 1.0:
            raise ValueError(f"{self.scenario_id}: secondary_fraction [0, 1) aralığında olmalı")
        if self.noise_ppm <= 0:
            raise ValueError(f"{self.scenario_id}: noise_ppm pozitif olmalı")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "scenario_id": self.scenario_id,
            "family": self.family,
            "index": self.index,
            "seed": self.seed,
            "expected": self.expected,
            "period_days": round(self.period_days, 6),
            "depth_ppm": round(self.depth * 1e6, 3),
            "observed_depth_ppm": round(self.depth * self.dilution * 1e6, 3),
            "duration_hours": round(self.duration_days * 24.0, 4),
            "t0_days": round(self.t0_days, 6),
            "steepness": round(self.steepness, 4),
            "dilution": round(self.dilution, 4),
            "secondary_fraction": round(self.secondary_fraction, 4),
            "alternate_ratio": round(self.alternate_ratio, 4),
            "variability_amplitude_ppm": round(self.variability_amplitude * 1e6, 3),
            "variability_period_days": round(self.variability_period_days, 4),
            "noise_ppm": round(self.noise_ppm, 3),
        }


def grid_sha256(scenarios: Sequence[AdversarialScenario]) -> str:
    """Korpusun kimliğini döndürür (senaryo tanımlarının sıralı canonical hash'i)."""

    payload = [scenario.to_dict() for scenario in scenarios]
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _trapezoid(phase_distance: np.ndarray, half_width: float, steepness: float) -> np.ndarray:
    """Faz mesafesi için 0-1 arası gölgeleme profili (0 = dışarıda, 1 = tam derinlik)."""

    flat = half_width * (1.0 - steepness)
    inside = phase_distance <= half_width
    ramp = (half_width - phase_distance) / max(half_width - flat, 1e-12)
    return np.where(inside, np.where(phase_distance <= flat, 1.0, np.clip(ramp, 0.0, 1.0)), 0.0)


def synthetic_lightcurve(
    scenario: AdversarialScenario,
    *,
    n_points: int = N_POINTS,
    baseline: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Deterministik ``(time, flux, flux_err)`` üretir.

    Üretim yıldız saat dilimi/gap simülasyonu içermez: zaman ızgarası düzgün
    aralıklıdır ve bu, korpusun ilan edilmiş bir sınırıdır.
    """

    scenario.validate()
    rng = np.random.default_rng(scenario.seed)
    time = np.arange(n_points, dtype=float) * CADENCE_DAYS
    flux = np.full(n_points, float(baseline), dtype=float)

    period = scenario.period_days
    half_width_phase = 0.5 * scenario.duration_days / period
    # Event fazı [-P/2, P/2): 0, birincil eclipse'un merkezindedir.
    phase = np.mod(time - scenario.t0_days + 0.5 * period, period) - 0.5 * period
    event_number = np.floor((time - scenario.t0_days) / period + 0.5)
    depth_scale = np.where(event_number % 2 == 0, 1.0, scenario.alternate_ratio)

    primary = _trapezoid(np.abs(phase), half_width_phase, scenario.steepness)
    flux -= primary * scenario.depth * scenario.dilution * depth_scale

    if scenario.secondary_fraction > 0.0:
        # Ikincil tutulma yorungede birincilden yarım periyot uzakta durur;
        # |phase| - P/2 mesafesi onu tam olarak faz 0.5'e koyar.
        secondary = _trapezoid(np.abs(np.abs(phase) - 0.5 * period), half_width_phase, scenario.steepness)
        flux -= secondary * scenario.depth * scenario.dilution * scenario.secondary_fraction

    if scenario.variability_amplitude > 0.0 and scenario.variability_period_days > 0.0:
        phase_offset = rng.uniform(0.0, 2.0 * math.pi)
        flux -= scenario.variability_amplitude * np.sin(
            2.0 * math.pi * time / scenario.variability_period_days + phase_offset
        )

    sigma = scenario.noise_ppm * 1e-6
    flux = flux + rng.normal(0.0, sigma, size=n_points)
    flux_err = np.full(n_points, sigma, dtype=float)
    return time, flux, flux_err


def classify_outcome(
    candidate: Any,
    quality_result: Any,
    *,
    reject_threshold: float = ADVERSARIAL_FPP_REJECT_THRESHOLD,
) -> dict[str, Any]:
    """Bir senaryonun pipeline sonucunu red/geçiş sınıfına çevirir.

    ``candidate`` ``None`` ise veya BLS hiç tepe bulmadıysa red **tespit
    kademesinde** olmuş sayılır. Vetting kararı ``is_false_positive`` bayrağı
    ya da eşik üstü heuristik FPP proxy'sidir; proxy ``None`` ise (hiçbir test
    ölçülemedi) red sayılmaz, çünkü yokluk kanıtı yoktur. Anomali raporlarından
    herhangi biri ``REJECT`` derse red ayrı bir kademe olarak sayılır.
    """

    observed: dict[str, Any] = {
        "outcome": LEAK_OUTCOME,
        "cascade_status": "",
        "candidate_confirmed": False,
        "vetting_is_false_positive": False,
        "fpp": None,
        "fpp_method": "",
        "fp_flags": [],
        "n_fail": 0,
        "n_warn": 0,
        "anomaly_flag": "",
        "anomaly_flags": {},
        "anomaly_score": None,
        "anomaly_n_severe": 0,
        "quality_score": None,
        "candidate_class": "",
        "secondary_eclipse_depth_ppm": None,
        "odd_even_mismatch": None,
        "depth_variance": None,
        "transit_symmetry": None,
    }
    if candidate is None or not getattr(candidate, "has_candidate", False):
        observed["outcome"] = "rejected_at_detection"
        observed["cascade_status"] = str(getattr(getattr(candidate, "status", None), "value", ""))
        return observed

    observed["cascade_status"] = str(getattr(getattr(candidate, "status", None), "value", candidate.status))
    observed["candidate_confirmed"] = bool(getattr(candidate, "confirmed", False))
    if not observed["candidate_confirmed"]:
        observed["outcome"] = "rejected_at_cascade"
        return observed

    vetting = getattr(quality_result, "vetting", None) if quality_result is not None else None
    if vetting is None:
        # Onaylanmış aday ama kalite kademesi çalışmadı: red iddiası kurulamaz.
        observed["outcome"] = LEAK_OUTCOME
        return observed

    flags = list(getattr(vetting, "fp_flags", []) or [])
    fpp = getattr(vetting, "false_positive_probability", None)
    observed["vetting_is_false_positive"] = bool(getattr(vetting, "is_false_positive", False))
    observed["fpp"] = None if fpp is None else round(float(fpp), 6)
    observed["fpp_method"] = str(getattr(vetting, "fpp_method", "") or "")
    observed["fp_flags"] = flags
    observed["n_fail"] = int(getattr(vetting, "n_fail", 0) or 0)
    observed["n_warn"] = int(getattr(vetting, "n_warn", 0) or 0)

    metrics = getattr(quality_result, "metrics", None)
    transit = getattr(metrics, "transit", None)
    stellar = getattr(metrics, "stellar", None)
    observed["secondary_eclipse_depth_ppm"] = _ppm(stellar, "secondary_eclipse_depth")
    observed["odd_even_mismatch"] = _round_or_none(getattr(transit, "odd_even_mismatch", None))
    observed["depth_variance"] = _round_or_none(getattr(transit, "depth_variance", None))
    observed["transit_symmetry"] = _round_or_none(getattr(transit, "transit_symmetry", None))
    score = getattr(quality_result, "score", None)
    observed["quality_score"] = _round_or_none(getattr(score, "quality_score", None))
    candidate_class = getattr(score, "candidate_class", None)
    observed["candidate_class"] = str(getattr(candidate_class, "value", candidate_class or ""))

    anomaly_flags: dict[str, str] = {}
    for attribute, label in (
        ("anomaly", "combined"),
        ("anomaly_residual", "residual"),
        ("anomaly_transit", "transit"),
        ("anomaly_timing", "timing"),
    ):
        report = getattr(quality_result, attribute, None)
        if report is None:
            continue
        anomaly_flags[label] = str(getattr(report, "anomaly_flag", "") or "")
    observed["anomaly_flags"] = anomaly_flags
    combined = getattr(quality_result, "anomaly", None)
    if combined is not None:
        observed["anomaly_flag"] = str(getattr(combined, "anomaly_flag", "") or "")
        observed["anomaly_score"] = _round_or_none(getattr(combined, "anomaly_score", None))
        observed["anomaly_n_severe"] = int(getattr(combined, "n_severe", 0) or 0)

    if observed["vetting_is_false_positive"] or (fpp is not None and float(fpp) >= reject_threshold):
        observed["outcome"] = "rejected_at_vetting"
    elif ANOMALY_REJECT_FLAG in anomaly_flags.values():
        observed["outcome"] = "rejected_at_anomaly"
    return observed


def _ppm(owner: Any, attribute: str) -> Optional[float]:
    value = getattr(owner, attribute, None) if owner is not None else None
    if value is None:
        return None
    return round(float(value) * 1e6, 4)


def _round_or_none(value: Any, digits: int = 6) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), digits)


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> Optional[tuple[float, float]]:
    """Wilson skoru aralığı; ``total == 0`` için ``None`` (uydurma aralık yok)."""

    if total <= 0:
        return None
    phat = successes / total
    denominator = 1.0 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def _count_by(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _median(values: Iterable[Optional[float]]) -> Optional[float]:
    clean = sorted(float(value) for value in values if value is not None)
    if not clean:
        return None
    middle = len(clean) // 2
    if len(clean) % 2:
        return round(clean[middle], 6)
    return round((clean[middle - 1] + clean[middle]) / 2.0, 6)


def _family_block(rows: list[Mapping[str, Any]], family: str) -> dict[str, Any]:
    member_rows = [row for row in rows if row.get("family") == family]
    expected = ADVERSARIAL_FAMILIES[family]["expected"]
    evaluated = [row for row in member_rows if str(row.get("outcome")) != "error"]
    rejected = sum(str(row.get("outcome")) in REJECTION_OUTCOMES for row in evaluated)
    accepted = sum(str(row.get("outcome")) == LEAK_OUTCOME for row in evaluated)
    interval = (
        wilson_interval(rejected, len(evaluated))
        if expected == "false_positive"
        else wilson_interval(accepted, len(evaluated))
    )
    return {
        "expected": expected,
        "targeted_test": ADVERSARIAL_FAMILIES[family]["targets_test"],
        "n_scenarios": len(member_rows),
        "n_evaluated": len(evaluated),
        "n_error": len(member_rows) - len(evaluated),
        "rejected_count": rejected if expected == "false_positive" else None,
        "leak_count": accepted if expected == "false_positive" else None,
        "accepted_count": accepted if expected == "planet" else None,
        "rejection_rate": (rejected / len(evaluated)) if (expected == "false_positive" and evaluated) else None,
        "control_acceptance_rate": (accepted / len(evaluated)) if (expected == "planet" and evaluated) else None,
        "rate_statistic": "rejection_rate" if expected == "false_positive" else "control_acceptance_rate",
        "rejected_by_stage": _count_by(evaluated, "outcome") if expected == "false_positive" else {},
        "wilson_interval_95": None if interval is None else [round(interval[0], 6), round(interval[1], 6)],
        "fpp_median_of_leaks": _median(
            [row.get("fpp") for row in evaluated if str(row.get("outcome")) == LEAK_OUTCOME]
        ),
    }


def build_adversarial_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    scenarios: Optional[Sequence[AdversarialScenario]] = None,
    reject_threshold: float = ADVERSARIAL_FPP_REJECT_THRESHOLD,
    minimum_per_family: int = 6,
    minimum_control_acceptance: float = 0.5,
    minimum_rejection_rate: float = 0.8,
    minimum_per_family_rejection_rate: float = 0.5,
    provenance: Optional[Mapping[str, Any]] = None,
    environment: Optional[Mapping[str, Any]] = None,
    method_notes: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Aile bazında red oranlarını ve kapı için iç geçerliği raporlar.

    ``status`` yalnızca tüm iç geçerlik koşulları sağlandığında ``measured``
    olur; aksi halde ``pending_run`` kalır ve ``blocking_reasons`` nedenleri
    taşır. Eşikler ölçümden **önce** ilan edilir (program.json).
    """

    materialized = [dict(row) for row in rows]
    if not materialized:
        raise ValueError("adversarial rapor en az bir sonuç satırı gerektirir.")

    families = {str(row.get("family")) for row in materialized}
    unknown = sorted(families - set(ADVERSARIAL_FAMILIES))
    if unknown:
        raise ValueError(f"bilinmeyen adversarial aile(ler): {unknown}")

    blocks = {family: _family_block(materialized, family) for family in sorted(ADVERSARIAL_FAMILIES)}
    missing_families = sorted(set(ADVERSARIAL_FAMILIES) - families)

    adversarial = [family for family in blocks if ADVERSARIAL_FAMILIES[family]["expected"] == "false_positive"]
    controls = [family for family in blocks if ADVERSARIAL_FAMILIES[family]["expected"] == "planet"]
    total_adversarial = sum(blocks[family]["n_evaluated"] for family in adversarial)
    rejected_adversarial = sum(blocks[family]["rejected_count"] or 0 for family in adversarial)
    total_controls = sum(blocks[family]["n_evaluated"] for family in controls)
    accepted_controls = sum(blocks[family]["accepted_count"] or 0 for family in controls)
    errors = sum(1 for row in materialized if str(row.get("outcome")) == "error")

    rejection_rate = rejected_adversarial / total_adversarial if total_adversarial else None
    control_acceptance = accepted_controls / total_controls if total_controls else None
    overall_interval = wilson_interval(rejected_adversarial, total_adversarial)

    blockers: list[str] = []
    if not total_adversarial:
        blockers.append("no_adversarial_families")
    if not total_controls:
        blockers.append("no_positive_control_family")
    if errors:
        blockers.append(f"error_rows:{errors}")
    for family in missing_families:
        blockers.append(f"family_missing_from_run:{family}")
    for family, block in blocks.items():
        if block["n_evaluated"] < minimum_per_family:
            blockers.append(f"family_below_minimum:{family}:{block['n_evaluated']}<{minimum_per_family}")
        if block["n_error"]:
            blockers.append(f"family_errors:{family}:{block['n_error']}")
    for family in adversarial:
        rate = blocks[family]["rejection_rate"]
        if rate is not None and rate < minimum_per_family_rejection_rate:
            blockers.append(
                f"family_rejection_below_floor:{family}:{round(rate, 4)}<{minimum_per_family_rejection_rate}"
            )
    if rejection_rate is None or rejection_rate < minimum_rejection_rate:
        blockers.append(
            f"overall_rejection_below_declared_floor:{'NA' if rejection_rate is None else round(rejection_rate, 4)}"
            f"<{minimum_rejection_rate}"
        )
    if total_controls and (control_acceptance is None or control_acceptance < minimum_control_acceptance):
        blockers.append(
            f"positive_control_acceptance_below_floor:{'NA' if control_acceptance is None else round(control_acceptance, 4)}"
            f"<{minimum_control_acceptance}"
        )

    return {
        "schema_version": "1.0",
        "campaign": "adversarial_false_positives_v1",
        "status": "measured" if not blockers else "pending_run",
        "blocking_reasons": blockers,
        "claim_policy": (
            "A gate closes only when its declared status and immutable evidence are measured/pass "
            "and every predeclared acceptance check passes; pending work is never a score."
        ),
        "method": {
            "data": "synthetic",
            "generator": "astrotransit/validation/adversarial_fp.py",
            "baseline_days": BASELINE_DAYS,
            "cadence_days": round(CADENCE_DAYS, 9),
            "cadence_seconds": 600.0,
            "n_points": N_POINTS,
            "noise_ppm": NOISE_PPM,
            "shape_model": "analytic trapezoid/V (steepness=1 triangle); no limb darkening, no batman",
            "rejection_definition": "no BLS peak, cascade non-confirmation, or vetting is_false_positive / fpp >= threshold",
            "fpp_reject_threshold": float(reject_threshold),
            "missing_fpp_treatment": "None is never read as zero risk",
            "detection_stage": "CascadeDetector (BLS->TLS) + QualityEvaluationPipeline vetting",
            "declared_floor_rejection_rate": float(minimum_rejection_rate),
            "declared_floor_control_acceptance": float(minimum_control_acceptance),
            "declared_floor_per_family_rejection_rate": float(minimum_per_family_rejection_rate),
            **dict(method_notes or {}),
        },
        "corpus": {
            "n_rows": len(materialized),
            "n_families": len(blocks),
            "families_missing_from_run": missing_families,
            "grid_sha256": None if scenarios is None else grid_sha256(scenarios),
            "n_scenarios": None if scenarios is None else len(scenarios),
        },
        "families": blocks,
        "overall": {
            "adversarial_scenarios": total_adversarial,
            "adversarial_rejected": rejected_adversarial,
            "adversarial_rejection_rate": None if rejection_rate is None else round(rejection_rate, 6),
            "adversarial_rejected_by_stage": _count_by(
                [row for row in materialized if str(row.get("outcome")) in REJECTION_OUTCOMES], "outcome"
            ),
            "adversarial_rejection_wilson_95": None
            if overall_interval is None
            else [round(overall_interval[0], 6), round(overall_interval[1], 6)],
            "control_scenarios": total_controls,
            "control_accepted": accepted_controls,
            "control_acceptance_rate": None if control_acceptance is None else round(control_acceptance, 6),
            "total_errors": errors,
        },
        "outcome_counts": _count_by(materialized, "outcome"),
        "environment": dict(environment or {}),
        "provenance": dict(provenance or {}),
        "claim_boundary": (
            "Synthetic adversarial morphologies on a uniform 600 s cadence with Gaussian noise. The "
            "measured rejection rate qualifies the pipeline's response to the specific shapes declared "
            "here; it is not a survey false-positive rate, not a completeness estimate for real TESS "
            "systematics, and not evidence about any individual target. The positive control family is "
            "included so that rejecting everything cannot score as success."
        ),
    }


__all__ = [
    "ADVERSARIAL_FAMILIES",
    "ADVERSARIAL_FPP_REJECT_THRESHOLD",
    "ANOMALY_REJECT_FLAG",
    "BASELINE_DAYS",
    "CADENCE_DAYS",
    "LEAK_OUTCOME",
    "N_POINTS",
    "NOISE_PPM",
    "REJECTION_OUTCOMES",
    "AdversarialScenario",
    "build_adversarial_report",
    "classify_outcome",
    "grid_sha256",
    "synthetic_lightcurve",
    "wilson_interval",
]
