"""Contract test for the TFOP-disposition labelled corpus (Gate 3 input).

The corpus (``benchmarks/corpora/tfop_disposition_corpus_v1.json``) is the
independent-label input for false-positive/precision/recall evaluation,
curated from the TESS FOP Working Group dispositions in
``benchmarks/toi_catalog.csv``. It is an *input*, not a measurement: the
pipeline has not been run on these targets, and no quiet-star controls are
included (they are not derivable from a candidate catalog).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from astrotransit.validation.corpus import ALLOWED_LABELS, corpus_summary, load_corpus

CORPUS_PATH = Path(__file__).resolve().parents[1] / "benchmarks" / "corpora" / "tfop_disposition_corpus_v1.json"
SOURCE_CSV = Path(__file__).resolve().parents[1] / "benchmarks" / "corpora" / "tfop_disposition_corpus_v1.csv"


def test_corpus_loads_through_contract_and_keeps_independent_labels():
    cases = load_corpus(CORPUS_PATH)
    assert cases, "corpus is empty"
    counts = Counter(case.label for case in cases)
    assert counts["false_positive"] >= 100, "gate requires >=100 labelled false positives"
    assert counts["planet"] > 0, "precision/recall evaluation needs positive controls"
    assert set(counts) <= ALLOWED_LABELS
    # Independent source of truth: every case must cite the TFOP disposition.
    for case in cases[:200]:
        assert "TESS FOP Working Group disposition" in case.reference
    # No quiet controls: the summary flag must stay False until a real
    # quiet-star list is curated from an independent source.
    summary = corpus_summary(cases)
    assert summary["has_negative_controls"] is False
    assert summary["has_false_positive_cases"] is True
    assert summary["n_cases"] == len(cases)


def test_frozen_corpus_matches_its_curation_source():
    payload = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    import hashlib

    assert hashlib.sha256(SOURCE_CSV.read_bytes()).hexdigest() == payload["source_csv_sha256"]
    assert payload["corpus_version"] == "1.0"
