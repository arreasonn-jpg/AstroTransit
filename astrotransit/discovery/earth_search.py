"""Earth-like adayların makine-okunur önceliklendirmesi.

Bu modül similarity skorunu detection confidence ve FPP ile tek bir "kanıt"
skoruna dönüştürmez. Bunun yerine operasyonel follow-up önceliği üretirken üç
bileşeni ayrı ayrı taşır; bilimsel kayıt üzerindeki Earth similarity değeri
her zaman bağımsız olarak okunabilir kalır.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Iterable, Sequence


_STATUS_LABELS = {
    "photometric_earth_like_candidate": "Photometric Earth-like candidate",
    "earth_twin_candidate": "Earth-twin candidate",
    "confirmed_earth_twin": "Confirmed Earth twin",
}

_STATUS_PRIORITY = {
    "photometric_earth_like_candidate": 70.0,
    "earth_twin_candidate": 85.0,
    "confirmed_earth_twin": 100.0,
}

_CONFIDENCE_SCORE = {
    "HIGH": 100.0,
    "MEDIUM": 70.0,
    "LOW": 25.0,
    "UNKNOWN": 15.0,
}


@dataclass(frozen=True)
class EarthCandidatePriority:
    """Tek hedef için follow-up önceliklendirme sonucu.

    ``similarity_score``, ``detection_confidence`` ve ``fpp`` ayrı alanlardır.
    ``priority_score`` yalnızca operasyonel sıralama içindir; bir olasılık veya
    Earth similarity skoru değildir.
    """

    target_id: str
    candidate_category: str
    category_label: str
    similarity_score: float
    similarity_p05: float
    similarity_p95: float
    similarity_completeness: float
    detection_confidence: str
    false_positive_probability: float | None
    priority_score: float
    search_channel: str
    source_sectors: tuple[int, ...] = ()
    candidate_class: str = ""
    long_period_identifiability: str = ""
    rationale: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "candidate_category": self.candidate_category,
            "category_label": self.category_label,
            "similarity_score": round(self.similarity_score, 4),
            "similarity_p05": round(self.similarity_p05, 4),
            "similarity_p95": round(self.similarity_p95, 4),
            "similarity_completeness": round(self.similarity_completeness, 4),
            "detection_confidence": self.detection_confidence,
            "false_positive_probability": self.false_positive_probability,
            "priority_score": round(self.priority_score, 4),
            "search_channel": self.search_channel,
            "source_sectors": list(self.source_sectors),
            "candidate_class": self.candidate_class,
            "long_period_identifiability": self.long_period_identifiability,
            "rationale": list(self.rationale),
        }


@dataclass(frozen=True)
class EarthSearchSummary:
    """Toplu TESS aramasının aday sıralama özeti."""

    n_targets: int
    n_records: int
    n_ranked_candidates: int
    ranked_candidates: tuple[EarthCandidatePriority, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_targets": self.n_targets,
            "n_records": self.n_records,
            "n_ranked_candidates": self.n_ranked_candidates,
            "ranked_candidates": [item.to_dict() for item in self.ranked_candidates],
        }

    def write_json(self, path: str | Path) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output


class EarthCandidateRanker:
    """Transit kayıtlarını Earth-like follow-up önceliğine göre sıralar.

    Varsayılan filtre yaklaşık yüzde 90 similarity eşiğini kullanır. Kayıtların
    ``earth_twin_status`` alanı kategoriyi taşır; eski kayıtlar için
    ``earth_analog_class`` geriye dönük fallback olarak desteklenir.
    """

    def __init__(
        self,
        *,
        min_similarity: float = 90.0,
        include_incomplete: bool = False,
        deduplicate_targets: bool = True,
    ):
        if not 0.0 <= min_similarity <= 100.0:
            raise ValueError("min_similarity 0 ile 100 arasında olmalıdır.")
        self.min_similarity = float(min_similarity)
        self.include_incomplete = include_incomplete
        self.deduplicate_targets = deduplicate_targets

    def rank(self, records: Iterable[Any]) -> list[EarthCandidatePriority]:
        """Kayıtları filtreler ve azalan operasyonel öncelikle sıralar."""

        candidates: list[EarthCandidatePriority] = []
        for record in records:
            priority = self._build_priority(record)
            if priority is not None:
                candidates.append(priority)

        if self.deduplicate_targets:
            best_by_target: dict[str, EarthCandidatePriority] = {}
            for candidate in candidates:
                previous = best_by_target.get(candidate.target_id)
                if previous is None or self._sort_key(candidate) < self._sort_key(previous):
                    best_by_target[candidate.target_id] = candidate
            candidates = list(best_by_target.values())

        return sorted(candidates, key=self._sort_key)

    def summarize(
        self,
        records: Iterable[Any],
        *,
        n_targets: int | None = None,
    ) -> EarthSearchSummary:
        materialized = list(records)
        ranked = tuple(self.rank(materialized))
        if n_targets is None:
            n_targets = len({self._target_id(record) for record in materialized})
        return EarthSearchSummary(
            n_targets=n_targets,
            n_records=len(materialized),
            n_ranked_candidates=len(ranked),
            ranked_candidates=ranked,
        )

    def rank_target_results(self, target_results: Iterable[Any]) -> list[EarthCandidatePriority]:
        """TESSPipeline sonuçlarından aday kayıtlarını çıkarıp sıralar."""

        return self.rank(self.records_from_target_results(target_results))

    @staticmethod
    def records_from_target_results(target_results: Iterable[Any]) -> list[Any]:
        records: list[Any] = []
        for target_result in target_results:
            for sector_result in getattr(target_result, "sector_results", []) or []:
                record = getattr(sector_result, "record", None)
                if record is not None:
                    records.append(record)
            long_period_record = getattr(target_result, "long_period_record", None)
            if long_period_record is not None:
                records.append(long_period_record)
        return records

    def _build_priority(self, record: Any) -> EarthCandidatePriority | None:
        status = self._category(record)
        if status is None:
            return None

        similarity = self._float(record, "earth_similarity_score", 0.0)
        if similarity < self.min_similarity:
            return None
        similarity_p05 = self._float(record, "earth_similarity_p05", similarity)
        similarity_p95 = self._float(record, "earth_similarity_p95", similarity)
        completeness = max(0.0, min(1.0, self._float(record, "earth_similarity_completeness", 0.0)))
        confidence = str(self._value(record, "detection_confidence", "UNKNOWN") or "UNKNOWN").upper()
        confidence_score = _CONFIDENCE_SCORE.get(confidence, _CONFIDENCE_SCORE["UNKNOWN"])
        fpp = self._optional_probability(record)
        fpp_score = 100.0 - 100.0 * fpp if fpp is not None else 15.0
        status_score = _STATUS_PRIORITY[status]

        # Follow-up önceliği; similarity, ölçüm tamlığı, tespit güveni/FPP ve
        # kategori olgunluğunu birleştirir. Bu değer olasılık değildir.
        priority_score = (
            0.55 * similarity
            + 0.15 * completeness * 100.0
            + 0.15 * confidence_score
            + 0.10 * fpp_score
            + 0.05 * status_score
        )

        rationale = [f"similarity={similarity:.1f}/100"]
        if similarity_p05 < similarity:
            rationale.append(f"similarity_p05={similarity_p05:.1f}")
        if completeness < 1.0:
            rationale.append(f"measurement_completeness={completeness:.2f}")
        rationale.append(f"detection_confidence={confidence}")
        if fpp is None:
            rationale.append("FPP=unknown")
        else:
            rationale.append(f"FPP={fpp:.3f}")

        return EarthCandidatePriority(
            target_id=self._target_id(record),
            candidate_category=status,
            category_label=_STATUS_LABELS[status],
            similarity_score=similarity,
            similarity_p05=similarity_p05,
            similarity_p95=similarity_p95,
            similarity_completeness=completeness,
            detection_confidence=confidence,
            false_positive_probability=fpp,
            priority_score=float(max(0.0, min(100.0, priority_score))),
            search_channel=str(self._value(record, "search_channel", "sector_cascade") or "sector_cascade"),
            source_sectors=self._source_sectors(record),
            candidate_class=str(self._value(record, "candidate_class", "") or ""),
            long_period_identifiability=str(
                self._value(record, "long_period_identifiability", "") or ""
            ),
            rationale=tuple(rationale),
        )

    def _category(self, record: Any) -> str | None:
        status = str(self._value(record, "earth_twin_status", "") or "").strip().lower()
        if status in _STATUS_LABELS:
            return status
        legacy = str(self._value(record, "earth_analog_class", "") or "").strip().upper()
        fallback = {
            "PHOTOMETRIC_EARTH_ANALOG": "photometric_earth_like_candidate",
            "EARTH_TWIN_CANDIDATE": "earth_twin_candidate",
            "CONFIRMED_EARTH_TWIN": "confirmed_earth_twin",
        }.get(legacy)
        if fallback is not None:
            return fallback
        if self.include_incomplete and status == "incomplete_earth_twin":
            return "photometric_earth_like_candidate"
        return None

    @staticmethod
    def _value(record: Any, name: str, default: Any = None) -> Any:
        if isinstance(record, dict):
            return record.get(name, default)
        return getattr(record, name, default)

    def _target_id(self, record: Any) -> str:
        return str(self._value(record, "source_id", self._value(record, "target_id", "")) or "")

    def _float(self, record: Any, name: str, default: float) -> float:
        try:
            value = float(self._value(record, name, default))
            return value if math.isfinite(value) else default
        except (TypeError, ValueError):
            return default

    def _optional_probability(self, record: Any) -> float | None:
        raw = self._value(record, "false_positive_probability", None)
        if raw is None:
            raw = self._value(record, "fpp", None)
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            return None
        return value

    def _source_sectors(self, record: Any) -> tuple[int, ...]:
        raw = self._value(record, "source_sectors", [])
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = []
        try:
            return tuple(int(value) for value in raw)
        except (TypeError, ValueError):
            return ()

    @staticmethod
    def _sort_key(candidate: EarthCandidatePriority) -> tuple[float, float, float, float, str]:
        # sorted(..., key=...) ascending; negatif değerler azalan sıralama sağlar.
        fpp = candidate.false_positive_probability
        return (
            -candidate.priority_score,
            -candidate.similarity_score,
            fpp if fpp is not None else 1.0,
            -_STATUS_PRIORITY.get(candidate.candidate_category, 0.0),
            candidate.target_id,
        )


__all__ = [
    "EarthCandidatePriority",
    "EarthCandidateRanker",
    "EarthSearchSummary",
]
