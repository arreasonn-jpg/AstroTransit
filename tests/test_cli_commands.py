"""cli/main.py için kapsamlı komut testleri.

Her komut için:
- Happy path (mocklu)
- Hata yolları (dosya yok, boş liste, geçersiz argüman)
- Çıkış kodları (Exit(0|1|2))
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from cli.main import app

runner = CliRunner()


# ───────────────────── Yardımcılar ─────────────────────

def _fake_target_result(target_id="TIC 123", success=True, **kw):
    defaults = dict(
        target_id=target_id,
        success=success,
        sectors_processed=[1, 2],
        candidates_found=2,
        candidates_confirmed=1,
        error=None,
        sector_results=[],
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class _FakeOrchestrator:
    """with-statement destekli sahte orchestrator."""

    last_kwargs = None
    last_batch_call = None
    last_single_call = None

    def __init__(self, **kwargs):
        _FakeOrchestrator.last_kwargs = kwargs
        self.settings = MagicMock()
        self.settings.benchmark.report_json = "bench_report.json"
        self.settings.benchmark.report_csv = "bench_report.csv"
        self.settings.model_dump.return_value = {"cfg": "test"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def run_single(self, target, sectors=None):
        _FakeOrchestrator.last_single_call = (target, sectors)
        return _fake_target_result(target_id=target)

    def run_batch(self, targets, sectors=None):
        _FakeOrchestrator.last_batch_call = (list(targets), sectors)
        return [_fake_target_result(target_id=t) for t in targets]

    def run_benchmark(self, max_per_category=None):
        return SimpleNamespace(
            performance_report=None,
            metrics=SimpleNamespace(report=lambda: "OK metrics"),
        )

    def close(self):
        pass


# ═══════════════════════════════════════════════════════
# version
# ═══════════════════════════════════════════════════════

def test_version_command():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "AstroTransit" in result.stdout


# ═══════════════════════════════════════════════════════
# single
# ═══════════════════════════════════════════════════════

def test_single_happy_path():
    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ):
        result = runner.invoke(app, ["single", "TIC 123"])
    assert result.exit_code == 0
    assert _FakeOrchestrator.last_single_call == ("TIC 123", None)


def test_single_with_sectors_and_flags():
    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ):
        result = runner.invoke(
            app,
            ["single", "261136679", "-s", "14", "-s", "15",
             "--force-mcmc", "--force-map", "--no-viz", "--no-catalog",
             "--log-level", "DEBUG"],
        )
    assert result.exit_code == 0
    kw = _FakeOrchestrator.last_kwargs
    assert kw["force_mcmc"] is True
    assert kw["force_map"] is True
    assert kw["skip_visualization"] is True
    assert kw["skip_catalog"] is True
    assert kw["log_level"] == "DEBUG"


def test_single_failed_result_shows_error():
    class FailingOrch(_FakeOrchestrator):
        def run_single(self, target, sectors=None):
            return _fake_target_result(
                target_id=target, success=False, error="boom"
            )

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        FailingOrch,
    ):
        result = runner.invoke(app, ["single", "TIC 1"])
    assert result.exit_code == 0
    assert "Başarısız" in result.stdout or "boom" in result.stdout


# ═══════════════════════════════════════════════════════
# batch
# ═══════════════════════════════════════════════════════

def test_batch_missing_file_exits_1(tmp_path):
    result = runner.invoke(app, ["batch", str(tmp_path / "nope.txt")])
    assert result.exit_code == 1
    assert "Dosya bulunamadı" in result.stdout


def test_batch_txt_file(tmp_path):
    f = tmp_path / "targets.txt"
    f.write_text("TIC 1\n# comment\nTIC 2\n\n", encoding="utf-8")

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ):
        result = runner.invoke(app, ["batch", str(f)])
    assert result.exit_code == 0
    targets, _ = _FakeOrchestrator.last_batch_call
    assert targets == ["TIC 1", "TIC 2"]


def test_batch_csv_file(tmp_path):
    import pandas as pd
    f = tmp_path / "targets.csv"
    pd.DataFrame({"tic_id": [111, 222]}).to_csv(f, index=False)

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ):
        result = runner.invoke(app, ["batch", str(f)])
    assert result.exit_code == 0
    targets, _ = _FakeOrchestrator.last_batch_call
    assert targets == ["TIC 111", "TIC 222"]


def test_batch_csv_without_tic_column(tmp_path):
    import pandas as pd
    f = tmp_path / "targets.csv"
    pd.DataFrame({"other": ["TIC 5", "TIC 6"]}).to_csv(f, index=False)

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ):
        result = runner.invoke(app, ["batch", str(f)])
    assert result.exit_code == 0


# ═══════════════════════════════════════════════════════
# target-pool
# ═══════════════════════════════════════════════════════

def test_target_pool_missing_file(tmp_path):
    result = runner.invoke(app, ["target-pool", str(tmp_path / "x.csv")])
    assert result.exit_code == 1


def test_target_pool_happy_path(tmp_path):
    src = tmp_path / "rows.json"
    src.write_text(json.dumps([{"tic_id": "123"}]), encoding="utf-8")
    dst = tmp_path / "out.json"

    class FakeBuilder:
        def __init__(self, cfg):
            self.cfg = cfg

        def build_from_rows(self, rows, query_coverage=False):
            return [SimpleNamespace(eligible=True), SimpleNamespace(eligible=False)]

        def write_json(self, entries, dest):
            Path(dest).write_text("[]")

        def write_csv(self, entries, dest):
            Path(dest).write_text("tic\n")

    fake_module = SimpleNamespace(
        EarthTargetPoolBuilder=FakeBuilder,
        TargetPoolConfig=lambda **kw: SimpleNamespace(**kw),
    )
    with patch.dict(
        "sys.modules",
        {"astrotransit.discovery.target_pool": fake_module},
    ):
        result = runner.invoke(app, ["target-pool", str(src), "-o", str(dst)])
    assert result.exit_code == 0
    assert "uygun bulundu" in result.stdout


def test_target_pool_invalid_json_list(tmp_path):
    src = tmp_path / "rows.json"
    src.write_text(json.dumps({"not": "list"}), encoding="utf-8")

    class FakeBuilder:
        def __init__(self, cfg): pass
        def build_from_rows(self, rows, query_coverage=False):
            raise TypeError("bad rows")

    fake_module = SimpleNamespace(
        EarthTargetPoolBuilder=FakeBuilder,
        TargetPoolConfig=lambda **kw: SimpleNamespace(**kw),
    )
    with patch.dict(
        "sys.modules",
        {"astrotransit.discovery.target_pool": fake_module},
    ):
        result = runner.invoke(
            app, ["target-pool", str(src), "-o", str(tmp_path / "o.json")]
        )
    assert result.exit_code == 1


# ═══════════════════════════════════════════════════════
# earth-search
# ═══════════════════════════════════════════════════════

def test_earth_search_limit_lt_1(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("TIC 1", encoding="utf-8")
    result = runner.invoke(app, ["earth-search", str(f), "--limit", "0"])
    assert result.exit_code == 1


def test_earth_search_similarity_out_of_range(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("TIC 1", encoding="utf-8")
    result = runner.invoke(
        app, ["earth-search", str(f), "--min-similarity", "150"]
    )
    assert result.exit_code == 1


def test_earth_search_missing_file(tmp_path):
    result = runner.invoke(app, ["earth-search", str(tmp_path / "no.txt")])
    assert result.exit_code == 1


def test_earth_search_empty_targets(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("# only comments\n\n", encoding="utf-8")
    result = runner.invoke(app, ["earth-search", str(f)])
    assert result.exit_code == 0


def test_earth_search_happy_path(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("TIC 1\nTIC 2\n", encoding="utf-8")

    class FakeRanker:
        def __init__(self, min_similarity=90.0):
            self.min = min_similarity

        def records_from_target_results(self, results):
            return [{"id": "TIC 1"}]

        def summarize(self, records, n_targets=0):
            return SimpleNamespace(
                n_targets=n_targets,
                n_records=1,
                n_ranked_candidates=0,
                ranked_candidates=(),
                write_json=lambda p: Path(p).write_text("{}") or Path(p),
            )

    fake_earth = SimpleNamespace(EarthCandidateRanker=FakeRanker)

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ), patch.dict(
        "sys.modules", {"astrotransit.discovery.earth_search": fake_earth}
    ):
        result = runner.invoke(app, ["earth-search", str(f)])
    assert result.exit_code == 0


class _FakeSummary:
    """EarthCandidateRanker.summarize dönüş tipi."""
    def __init__(self, n_targets=0, n_records=0,
                 n_ranked_candidates=0, ranked_candidates=()):
        self.n_targets = n_targets
        self.n_records = n_records
        self.n_ranked_candidates = n_ranked_candidates
        self.ranked_candidates = tuple(ranked_candidates)

    def write_json(self, p):
        Path(p).write_text("{}", encoding="utf-8")
        return Path(p)


def test_earth_search_with_output(tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("TIC 1\n", encoding="utf-8")
    out = tmp_path / "out.json"

    class FakeRanker:
        def __init__(self, min_similarity=90.0):
            pass
        def records_from_target_results(self, results):
            return []
        def summarize(self, records, n_targets=0):
            return _FakeSummary(n_targets=n_targets)

    fake_earth = SimpleNamespace(EarthCandidateRanker=FakeRanker)

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        _FakeOrchestrator,
    ), patch.dict(
        "sys.modules", {"astrotransit.discovery.earth_search": fake_earth}
    ):
        result = runner.invoke(
            app, ["earth-search", str(f), "-o", str(out)]
        )
    assert result.exit_code == 0, result.stdout


# ═══════════════════════════════════════════════════════
# followup-update
# ═══════════════════════════════════════════════════════

def test_followup_update_missing_evidence(tmp_path):
    result = runner.invoke(
        app,
        ["followup-update", "TIC 1", "1", str(tmp_path / "no.json")],
    )
    assert result.exit_code == 1


def test_followup_update_invalid_json(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text("{not json", encoding="utf-8")
    result = runner.invoke(
        app, ["followup-update", "TIC 1", "1", str(f)]
    )
    assert result.exit_code == 1


def test_followup_update_non_object_json(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text("[1,2,3]", encoding="utf-8")
    result = runner.invoke(
        app, ["followup-update", "TIC 1", "1", str(f)]
    )
    assert result.exit_code == 1


def test_followup_update_record_not_found(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text(json.dumps({"x": 1}), encoding="utf-8")

    class FakeMgr:
        def __init__(self, output_dir="outputs"): pass
        def find_record(self, tid, sector): return None
        def close(self): pass

    fake_writers = SimpleNamespace(OutputManager=FakeMgr)
    fake_ids = SimpleNamespace(normalize_tic_id=lambda x: x)

    with patch.dict("sys.modules", {
        "astrotransit.outputs.writers": fake_writers,
        "astrotransit.utils.identifiers": fake_ids,
    }):
        result = runner.invoke(
            app, ["followup-update", "TIC 1", "1", str(f)]
        )
    assert result.exit_code == 1


def test_followup_update_happy_path(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text(json.dumps({"status": "ok"}), encoding="utf-8")

    updated = SimpleNamespace(
        source_id="TIC 1", sector=1, followup_status="done",
        earth_twin_status="candidate",
    )

    class FakeMgr:
        def __init__(self, output_dir="outputs"): pass
        def find_record(self, tid, sector): return {"x": 1}
        def update_followup(self, rec, ev): return updated
        def close(self): pass

    fake_writers = SimpleNamespace(OutputManager=FakeMgr)
    fake_ids = SimpleNamespace(normalize_tic_id=lambda x: x)

    with patch.dict("sys.modules", {
        "astrotransit.outputs.writers": fake_writers,
        "astrotransit.utils.identifiers": fake_ids,
    }):
        result = runner.invoke(
            app, ["followup-update", "TIC 1", "1", str(f)]
        )
    assert result.exit_code == 0
    assert "güncellendi" in result.stdout


def test_followup_update_normalize_failure(tmp_path):
    f = tmp_path / "ev.json"
    f.write_text(json.dumps({"x": 1}), encoding="utf-8")

    class FakeMgr:
        def __init__(self, output_dir="outputs"): pass
        def find_record(self, tid, sector): return None
        def close(self): pass

    def boom(x):
        raise ValueError("bad id")

    fake_writers = SimpleNamespace(OutputManager=FakeMgr)
    fake_ids = SimpleNamespace(normalize_tic_id=boom)

    with patch.dict("sys.modules", {
        "astrotransit.outputs.writers": fake_writers,
        "astrotransit.utils.identifiers": fake_ids,
    }):
        result = runner.invoke(
            app, ["followup-update", "??", "1", str(f)]
        )
    assert result.exit_code == 1


# ═══════════════════════════════════════════════════════
# migrate
# ═══════════════════════════════════════════════════════

def test_migrate_missing_file(tmp_path):
    result = runner.invoke(app, ["migrate", str(tmp_path / "x.json")])
    assert result.exit_code == 1


def test_migrate_unsupported_extension(tmp_path):
    f = tmp_path / "x.txt"
    f.write_text("nope")
    result = runner.invoke(app, ["migrate", str(f)])
    assert result.exit_code == 2


def test_migrate_json_happy(tmp_path):
    src = tmp_path / "in.json"
    src.write_text("{}", encoding="utf-8")
    dst = tmp_path / "out.json"

    fake = SimpleNamespace(
        migrate_json=lambda s, o: Path(o),
        migrate_parquet=lambda s, o: Path(o),
    )
    with patch.dict("sys.modules", {"astrotransit.outputs.migration": fake}):
        result = runner.invoke(
            app, ["migrate", str(src), "-o", str(dst)]
        )
    assert result.exit_code == 0
    assert "migration" in result.stdout.lower()


def test_migrate_parquet_happy(tmp_path):
    src = tmp_path / "in.parquet"
    src.write_bytes(b"\x00")
    dst = tmp_path / "out.parquet"

    fake = SimpleNamespace(
        migrate_json=lambda s, o: Path(o),
        migrate_parquet=lambda s, o: Path(o),
    )
    with patch.dict("sys.modules", {"astrotransit.outputs.migration": fake}):
        result = runner.invoke(
            app, ["migrate", str(src), "-o", str(dst)]
        )
    assert result.exit_code == 0


def test_migrate_failure_raises_exit_1(tmp_path):
    src = tmp_path / "in.json"
    src.write_text("{}", encoding="utf-8")

    def boom(s, o):
        raise ValueError("nope")

    fake = SimpleNamespace(migrate_json=boom, migrate_parquet=boom)
    with patch.dict("sys.modules", {"astrotransit.outputs.migration": fake}):
        result = runner.invoke(app, ["migrate", str(src)])
    assert result.exit_code == 1


# ═══════════════════════════════════════════════════════
# benchmark
# ═══════════════════════════════════════════════════════

def test_benchmark_no_report(monkeypatch):
    class Orch(_FakeOrchestrator):
        def __init__(self, **kw):
            super().__init__(**kw)

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        Orch,
    ):
        result = runner.invoke(app, ["benchmark"])
    assert result.exit_code == 0


def test_benchmark_with_report(tmp_path, monkeypatch):
    from dataclasses import dataclass, field

    @dataclass
    class Report:
        provenance: dict = field(default_factory=dict)
        def to_dict(self):
            return {}
        def write_csv(self, p):
            Path(p).write_text("a")
        def summary(self):
            return "summary"

    class Orch(_FakeOrchestrator):
        def run_benchmark(self, max_per_category=None):
            return SimpleNamespace(
                performance_report=Report(),
                metrics=SimpleNamespace(report=lambda: "metrics"),
            )

    fake_prov = SimpleNamespace(build_manifest=lambda config=None: {"cfg": 1})
    fake_art = SimpleNamespace(write_artifact=lambda d, p: Path(p).write_text("{}"))

    with patch(
        "astrotransit.pipelines.orchestrator.AstroTransitOrchestrator",
        Orch,
    ), patch.dict("sys.modules", {
        "astrotransit.validation.provenance": fake_prov,
        "astrotransit.validation.artifacts": fake_art,
    }):
        result = runner.invoke(
            app,
            ["benchmark", "--output", str(tmp_path / "r.json"),
             "--csv-output", str(tmp_path / "r.csv")],
        )
    assert result.exit_code == 0


# ═══════════════════════════════════════════════════════
# reproduce
# ═══════════════════════════════════════════════════════

def test_reproduce_unknown_dataset():
    result = runner.invoke(app, ["reproduce", "unknown-dataset"])
    assert result.exit_code == 2


def test_reproduce_missing_output(tmp_path):
    fake_prov = SimpleNamespace(
        build_manifest=lambda config=None: {},
        sha256_file=lambda p: "deadbeef",
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.provenance": fake_prov,
    }), patch("cli.main.benchmark") as mock_bench:
        result = runner.invoke(
            app,
            ["reproduce", "benchmark-v1",
             "--output", str(tmp_path / "missing.json")],
        )
    assert result.exit_code == 1
    mock_bench.assert_called_once()


def test_reproduce_hash_mismatch(tmp_path):
    out = tmp_path / "out.json"
    out.write_text("{}")

    fake_prov = SimpleNamespace(
        build_manifest=lambda config=None: {},
        sha256_file=lambda p: "aaaa",
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.provenance": fake_prov,
    }), patch("cli.main.benchmark"):
        result = runner.invoke(
            app,
            ["reproduce", "benchmark-v1",
             "--output", str(out),
             "--expected-sha256", "bbbb"],
        )
    assert result.exit_code == 1


def test_reproduce_happy(tmp_path):
    out = tmp_path / "out.json"
    out.write_text("{}")
    manifest = tmp_path / "m.json"

    fake_prov = SimpleNamespace(
        build_manifest=lambda config=None: {"cfg": 1},
        sha256_file=lambda p: "aaaa",
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.provenance": fake_prov,
    }), patch("cli.main.benchmark"):
        result = runner.invoke(
            app,
            ["reproduce", "benchmark-v1",
             "--output", str(out),
             "--manifest", str(manifest)],
        )
    assert result.exit_code == 0
    assert manifest.exists()


# ═══════════════════════════════════════════════════════
# release-gate
# ═══════════════════════════════════════════════════════

def test_release_gate_no_data_fails(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    fake_corpus = SimpleNamespace(
        corpus_summary=lambda cases: {
            "counts": {"false_positive": 0, "quiet_star": 0}
        },
        load_corpus=lambda p: [],
    )
    fake_gate = SimpleNamespace(
        evaluate_release_gates=lambda **kw: SimpleNamespace(
            passed=False,
            to_dict=lambda: {"passed": False},
        )
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.corpus": fake_corpus,
        "astrotransit.validation.release_gate": fake_gate,
    }):
        result = runner.invoke(app, ["release-gate"])
    assert result.exit_code == 1


def test_release_gate_passed(tmp_path):
    fake_corpus = SimpleNamespace(
        corpus_summary=lambda cases: {
            "counts": {"false_positive": 3, "quiet_star": 2}
        },
        load_corpus=lambda p: [{"x": 1}],
    )
    fake_gate = SimpleNamespace(
        evaluate_release_gates=lambda **kw: SimpleNamespace(
            passed=True,
            to_dict=lambda: {"passed": True},
        )
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.corpus": fake_corpus,
        "astrotransit.validation.release_gate": fake_gate,
    }):
        result = runner.invoke(app, ["release-gate"])
    assert result.exit_code == 0


# ═══════════════════════════════════════════════════════
# evaluate-corpus
# ═══════════════════════════════════════════════════════

def test_evaluate_corpus_happy(tmp_path):
    preds = tmp_path / "preds.json"
    preds.write_text(json.dumps([{"target_id": "T1", "detected": True}]))

    class Case:
        def __init__(self, tid): self.target_id = tid

    fake_corpus = SimpleNamespace(load_corpus=lambda p: [Case("T1")])
    fake_eval = SimpleNamespace(
        evaluate_corpus=lambda cases, fn, split, seed: SimpleNamespace(
            errors=[],
            n_evaluated=len(cases),
            n_cases=len(cases),
            to_dict=lambda: {"ok": True},
        )
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.corpus": fake_corpus,
        "astrotransit.validation.corpus_evaluation": fake_eval,
    }):
        result = runner.invoke(
            app, ["evaluate-corpus", "corpus.json", str(preds)]
        )
    assert result.exit_code == 0


def test_evaluate_corpus_bad_predictions(tmp_path):
    preds = tmp_path / "preds.json"
    preds.write_text(json.dumps({"single": "dict"}))

    fake_corpus = SimpleNamespace(load_corpus=lambda p: [])
    fake_eval = SimpleNamespace(evaluate_corpus=lambda *a, **k: None)

    with patch.dict("sys.modules", {
        "astrotransit.validation.corpus": fake_corpus,
        "astrotransit.validation.corpus_evaluation": fake_eval,
    }):
        # dict with "predictions" key absent -> rows remains dict
        result = runner.invoke(
            app, ["evaluate-corpus", "c.json", str(preds)]
        )
    assert result.exit_code != 0


def test_evaluate_corpus_with_errors(tmp_path):
    preds = tmp_path / "preds.json"
    preds.write_text(json.dumps([{"target_id": "T1", "detected": True}]))

    fake_corpus = SimpleNamespace(load_corpus=lambda p: [1, 2])
    fake_eval = SimpleNamespace(
        evaluate_corpus=lambda *a, **k: SimpleNamespace(
            errors=["oops"],
            n_evaluated=1,
            n_cases=2,
            to_dict=lambda: {"errors": ["oops"]},
        )
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.corpus": fake_corpus,
        "astrotransit.validation.corpus_evaluation": fake_eval,
    }):
        result = runner.invoke(
            app, ["evaluate-corpus", "c.json", str(preds)]
        )
    assert result.exit_code == 1


# ═══════════════════════════════════════════════════════
# evaluate-fpp
# ═══════════════════════════════════════════════════════

def test_evaluate_fpp_happy(tmp_path):
    preds = tmp_path / "p.json"
    preds.write_text(json.dumps([
        {"target_id": "T1", "is_false_positive": False, "fpp": 0.1}
    ]))

    class R:
        def to_dict(self): return {"ok": True}

    fake = SimpleNamespace(
        FPPBenchmarkCase=lambda *a: ("case", a),
        evaluate_fpp_holdout=lambda cases, threshold, seed: {"split_a": R()},
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.fpp_benchmark": fake,
    }):
        result = runner.invoke(app, ["evaluate-fpp", str(preds)])
    assert result.exit_code == 0


def test_evaluate_fpp_dict_wrapper(tmp_path):
    preds = tmp_path / "p.json"
    preds.write_text(json.dumps({"cases": [
        {"target_id": "T1", "is_false_positive": True, "fpp": 0.9}
    ]}))

    class R:
        def to_dict(self): return {}

    fake = SimpleNamespace(
        FPPBenchmarkCase=lambda *a: ("case", a),
        evaluate_fpp_holdout=lambda cases, threshold, seed: {"s": R()},
    )
    with patch.dict("sys.modules", {
        "astrotransit.validation.fpp_benchmark": fake,
    }):
        result = runner.invoke(app, ["evaluate-fpp", str(preds)])
    assert result.exit_code == 0
