"""Validate and freeze an externally curated labelled validation corpus.

Input CSV must contain target_id,label,reference. The script intentionally does
not infer labels from names or catalog flags; curation and citation are part of
the scientific input.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from astrotransit.validation.corpus import ALLOWED_LABELS, CorpusCase


def load_csv(path: Path) -> list[CorpusCase]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        required = {"target_id", "label", "reference"}
        if not rows.fieldnames or not required.issubset(rows.fieldnames):
            raise ValueError("CSV required columns: target_id,label,reference")
        cases = []
        for row in rows:
            cases.append(CorpusCase(
                target_id=str(row["target_id"]).strip(),
                label=str(row["label"]).strip(),
                reference=str(row["reference"]).strip(),
                sectors=tuple(int(item) for item in str(row.get("sectors", "")).split(",") if item.strip()),
                notes=str(row.get("notes", "")).strip(),
            ))
    ids = [case.target_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("Corpus target_id değerleri unique olmalıdır")
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    cases = load_csv(args.input)
    if not cases:
        raise SystemExit("Empty corpus; no output written.")
    payload = {
        "corpus_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_csv_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "allowed_labels": sorted(ALLOWED_LABELS),
        "cases": [case.to_dict() for case in cases],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(cases)} labelled cases to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
