"""Versioned labelled validation-corpus contracts.

The repository intentionally does not invent astrophysical labels. This loader
only accepts explicit ``planet``, ``false_positive`` or ``quiet_star`` labels.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


ALLOWED_LABELS = frozenset({"planet", "false_positive", "quiet_star"})


@dataclass(frozen=True)
class CorpusCase:
    target_id: str
    label: str
    reference: str = ""
    sectors: tuple[int, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.target_id.strip():
            raise ValueError("Corpus target_id boş olamaz.")
        if self.label not in ALLOWED_LABELS:
            raise ValueError(f"Geçersiz corpus etiketi: {self.label}")
        if not self.reference.strip():
            raise ValueError("Corpus ground-truth kaydı reference gerektirir.")

    def to_dict(self) -> dict[str, Any]:
        return {"target_id": self.target_id, "label": self.label,
                "reference": self.reference, "sectors": list(self.sectors), "notes": self.notes}


def load_corpus(path: str | Path) -> list[CorpusCase]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    rows = payload.get("cases", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("Corpus JSON'u cases listesi içermelidir.")
    return [CorpusCase(
        target_id=str(row["target_id"]),
        label=str(row["label"]),
        reference=str(row.get("reference", "")),
        sectors=tuple(int(item) for item in row.get("sectors", ())),
        notes=str(row.get("notes", "")),
    ) for row in rows]


def corpus_summary(cases: Iterable[CorpusCase]) -> dict[str, Any]:
    materialized = list(cases)
    counts = {label: sum(item.label == label for item in materialized) for label in sorted(ALLOWED_LABELS)}
    return {"n_cases": len(materialized), "counts": counts,
            "has_negative_controls": counts["quiet_star"] > 0,
            "has_false_positive_cases": counts["false_positive"] > 0}


__all__ = ["ALLOWED_LABELS", "CorpusCase", "corpus_summary", "load_corpus"]
