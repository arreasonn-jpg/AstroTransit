"""Curate an independent-label planet/false-positive corpus from the TOI catalog.

The ``tfopwg_disp`` column of ``benchmarks/toi_catalog.csv`` carries the
TESS FOP Working Group disposition — an *independent* vetting program, not
an AstroTransit output. Dispositions map onto the corpus contract
(``astrotransit.validation.corpus.ALLOWED_LABELS``) as follows:

    FP   (false positive)              -> false_positive
    FA   (false alarm)                 -> false_positive
    APC  (astrophysical confirmed, i.e. a confirmed non-planet object)
                                        -> false_positive
    KP   (known planet)                -> planet
    CP   (confirmed planet)            -> planet
    PC   (planetary candidate)         -> EXCLUDED (no independent label)

This script produces a human-auditable curation CSV; it does NOT freeze the
corpus. Freezing is a separate, explicit step through the existing contract
tool:

    python scripts/validation/build_labelled_corpus.py \
        benchmarks/corpora/tfop_disposition_corpus_v1.csv \
        --output benchmarks/corpora/tfop_disposition_corpus_v1.json

Limitations (kept visible on purpose):

* This is an *input* corpus for FPR/specificity/precision/recall evaluation
  (Gate 3 / release-acceptance "False positives"). It is not a measurement;
  no pipeline run has been performed on these targets here.
* ``quiet_star`` negative controls are NOT derivable from the TOI catalog
  (every row is a candidate). They require an independent quiet-star list
  (e.g. TICs with no TOI history plus an occurrence/upper-limit argument)
  and remain PENDING DATA.
* ``APC`` objects (EBs, LRS, ...) are non-planet by construction; they are
  the strongest "false positive for a planet pipeline" class.
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

DISPOSITION_TO_LABEL = {
    "FP": "false_positive",
    "FA": "false_positive",
    "APC": "false_positive",
    "KP": "planet",
    "CP": "planet",
}
REFERENCE_TEMPLATE = (
    "TESS FOP Working Group disposition '{disp}' via NASA Exoplanet Archive "
    "TESS FOP WG catalog snapshot (benchmarks/toi_catalog.csv, accessed 2026-09-08)"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, default=Path("benchmarks/toi_catalog.csv"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmarks/corpora/tfop_disposition_corpus_v1.csv"),
    )
    args = parser.parse_args()

    per_target_disp: dict[str, set[str]] = {}
    tois: dict[str, list[str]] = {}
    disposition_counts = Counter()
    with args.input.open(newline="", encoding="utf-8-sig") as handle:
        for record in csv.DictReader(handle):
            disposition = (record.get("tfopwg_disp") or "").strip().upper()
            if disposition not in DISPOSITION_TO_LABEL:
                continue
            tid = (record.get("tid") or "").strip()
            if not tid:
                continue
            toi = (record.get("toi") or "").strip()
            disposition_counts[disposition] += 1
            per_target_disp.setdefault(tid, set()).add(disposition)
            if toi:
                tois.setdefault(tid, []).append(toi)

    rows: list[dict[str, str]] = []
    conflicts: list[tuple[str, set[str]]] = []
    for tid, dispositions in sorted(per_target_disp.items(), key=lambda item: int(item[0]) if item[0].isdigit() else 0):
        labels = {DISPOSITION_TO_LABEL[disposition] for disposition in dispositions}
        if len(labels) == 1:
            reference = "; ".join(
                REFERENCE_TEMPLATE.format(disp=disposition) for disposition in sorted(dispositions)
            )
            rows.append({
                "target_id": tid,
                "label": next(iter(labels)),
                "reference": reference,
                "notes": "TOI " + ", ".join(sorted(tois[tid])) if tois.get(tid) else "",
            })
        else:
            conflicts.append((tid, labels))

    rows.sort(key=lambda row: (row["label"], row["target_id"]))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["target_id", "label", "reference", "notes"])
        writer.writeheader()
        writer.writerows(rows)

    label_counts = Counter(row["label"] for row in rows)
    print(f"Wrote {len(rows)} curated cases to {args.output}")
    for label in sorted(label_counts):
        print(f"  {label}: {label_counts[label]}")
    for disposition in sorted(disposition_counts):
        print(f"  {disposition} -> {DISPOSITION_TO_LABEL[disposition]}: {disposition_counts[disposition]}")
    if label_counts.get("false_positive", 0) < 100:
        print("WARNING: fewer than 100 false_positive cases; gate requirement not met.")
    if conflicts:
        print(f"EXCLUDED {len(conflicts)} targets with conflicting TFOP dispositions (manual curation needed):")
        for tid, labels in conflicts[:20]:
            print(f"  TIC {tid}: {sorted(labels)}")
    print("Quiet-star controls are NOT included (not derivable from this catalog); see docstring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
