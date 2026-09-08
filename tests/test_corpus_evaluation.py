from astrotransit.validation.corpus import CorpusCase
from astrotransit.validation.corpus_evaluation import evaluate_corpus


def test_corpus_evaluation_keeps_errors_separate():
    cases = [
        CorpusCase("TIC 1", "planet", "ref"),
        CorpusCase("TIC 2", "quiet_star", "ref"),
    ]
    result = evaluate_corpus(cases, lambda case: (_ for _ in ()).throw(RuntimeError()) if case.target_id == "TIC 1" else False, split="all")
    assert result.errors == 1
    assert result.n_evaluated == 1
    assert result.true_negatives == 1
    assert result.false_negatives == 0
