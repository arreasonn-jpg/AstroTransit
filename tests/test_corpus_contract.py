import json

import pytest

from astrotransit.validation.corpus import CorpusCase, corpus_summary, load_corpus


def test_corpus_rejects_missing_reference():
    with pytest.raises(ValueError):
        CorpusCase("TIC 1", "false_positive")


def test_corpus_keeps_quiet_controls_distinct(tmp_path):
    path = tmp_path / "corpus.json"
    path.write_text(json.dumps({"cases": [
        {"target_id": "TIC 1", "label": "false_positive", "reference": "eb-catalog"},
        {"target_id": "TIC 2", "label": "quiet_star", "reference": "quiet-catalog"},
    ]}))
    cases = load_corpus(path)
    summary = corpus_summary(cases)
    assert summary["has_false_positive_cases"]
    assert summary["has_negative_controls"]
    assert summary["counts"]["planet"] == 0
