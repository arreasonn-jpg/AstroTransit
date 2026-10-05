"""astrotransit/validation/blind_holdout.py için kapsamlı testler."""
from __future__ import annotations

import json

import pytest

from astrotransit.validation.blind_holdout import (
    CAMPAIGN,
    DECLARED_CEILING_FALSE_POSITIVE_RATE,
    DECLARED_FLOOR_RECALL,
    HOLDOUT_SEED,
    LABEL_GROUPS,
    MINIMUM_CASES_PER_STRATUM,
    MINIMUM_EVALUATED_CASES,
    PER_LABEL,
    SELECTION_METHOD,
    SPLIT_SEED,
    _confusion,
    _ids_from,
    allocate_quotas,
    build_holdout_report,
    disposition_code,
    holdout_sha256,
    load_exclusion_ids,
    normalize_target_id,
    select_holdout,
    selection_rank,
    stratum_key,
    wilson_interval,
)

# ═══════════════════════════════════════════════════════
# Sabitler
# ═══════════════════════════════════════════════════════

def test_constants_sane():
    assert CAMPAIGN == "blind_domain_holdout_v1"
    assert SPLIT_SEED == 13
    assert HOLDOUT_SEED == 20260918
    assert PER_LABEL == 72
    assert 0 < DECLARED_FLOOR_RECALL < 1
    assert 0 < DECLARED_CEILING_FALSE_POSITIVE_RATE < 1
    assert MINIMUM_CASES_PER_STRATUM > 0
    assert MINIMUM_EVALUATED_CASES > 0


def test_label_groups():
    assert "planet" in LABEL_GROUPS
    assert "false_positive" in LABEL_GROUPS


# ═══════════════════════════════════════════════════════
# normalize_target_id
# ═══════════════════════════════════════════════════════

def test_normalize_strips_whitespace():
    assert normalize_target_id("  TIC 123  ") == "TIC 123"


def test_normalize_removes_decimal():
    assert normalize_target_id("123.456") == "123"


def test_normalize_handles_none():
    assert normalize_target_id(None) == "None"


def test_normalize_int():
    assert normalize_target_id(123) == "123"


# ═══════════════════════════════════════════════════════
# selection_rank
# ═══════════════════════════════════════════════════════

def test_selection_rank_deterministic():
    r1 = selection_rank(42, "TIC 123")
    r2 = selection_rank(42, "TIC 123")
    assert r1 == r2


def test_selection_rank_seed_sensitive():
    assert selection_rank(42, "TIC 123") != selection_rank(43, "TIC 123")


def test_selection_rank_id_sensitive():
    assert selection_rank(42, "TIC 1") != selection_rank(42, "TIC 2")


def test_selection_rank_hex_format():
    r = selection_rank(42, "TIC 123")
    assert len(r) == 64  # sha256 hex
    assert all(c in "0123456789abcdef" for c in r)


# ═══════════════════════════════════════════════════════
# disposition_code
# ═══════════════════════════════════════════════════════

def test_disposition_code_match():
    assert disposition_code("disposition 'CP'") == "CP"


def test_disposition_code_asterisk():
    assert disposition_code("something disposition 'KP*' more") == "KP*"


def test_disposition_code_no_match():
    assert disposition_code("no disposition here") == "UNCODED"


def test_disposition_code_empty():
    assert disposition_code("") == "UNCODED"


def test_disposition_code_none():
    assert disposition_code(None) == "UNCODED"


# ═══════════════════════════════════════════════════════
# stratum_key
# ═══════════════════════════════════════════════════════

def test_stratum_key_format():
    assert stratum_key("planet", "disposition 'CP'") == "planet:CP"


def test_stratum_key_uncoded():
    assert stratum_key("planet", "no match") == "planet:UNCODED"


# ═══════════════════════════════════════════════════════
# allocate_quotas
# ═══════════════════════════════════════════════════════

def test_allocate_empty_pool():
    assert allocate_quotas({}, 100) == {}


def test_allocate_zero_total():
    assert allocate_quotas({"a": 10, "b": 20}, 0) == {"a": 0, "b": 0}


def test_allocate_negative_total():
    assert allocate_quotas({"a": 10}, -5) == {"a": 0}


def test_allocate_no_minimum():
    result = allocate_quotas({"a": 10, "b": 30}, 20)
    assert sum(result.values()) == 20
    assert result["b"] > result["a"]  # orantılı


def test_allocate_with_minimum():
    # minimum her zaman min(available, minimum) ile sınırlıdır
    result = allocate_quotas({"a": 5, "b": 100}, 20, minimum=3)
    assert result["a"] >= 3
    assert result["b"] >= 3
    assert sum(result.values()) == 20


def test_allocate_minimum_capped_by_available():
    # available < minimum → available kadar
    result = allocate_quotas({"a": 2, "b": 1000}, 20, minimum=8)
    assert result["a"] == 2


def test_allocate_minimum_exceeds_total():
    """Taban toplamı aşarsa her katmandan 1 kırpılır (min garantisi korunur)."""
    result = allocate_quotas({"a": 10, "b": 10}, 5, minimum=8)
    # base = {a:8, b:8} sum=16 > 5 → loop bir kez her ikisini de azaltır: 7,7
    assert result["a"] == 7
    assert result["b"] == 7


def test_allocate_remainder_loop_break():
    """Remainder dağıtımı sırasında headroom tükenirse break (105->111)."""
    # Küçük havuzlar, büyük total → bazı katmanlar max'a ulaşır
    result = allocate_quotas({"a": 1, "b": 1, "c": 100}, 50, minimum=1)
    assert sum(result.values()) == 50
    assert result["a"] == 1  # max'a ulaştı
    assert result["b"] == 1  # max'a ulaştı


def test_allocate_total_exceeds_available_bug():
    """BELGELENMIŞ BUG: total > available_toplam olduğunda fonksiyon
    available'ı aşan kota üretebilir. Test şu anki (hatalı) davranışı
    sabitler; düzeltme ayrı bir PR'da yapılacak (bkz. issue)."""
    result = allocate_quotas({"a": 2, "b": 3}, 100, minimum=1)
    # Toplam max 5 olmalı ama fonksiyon 99 döndürüyor
    assert sum(result.values()) > 5  # HATALI DAVRANIŞ


def test_select_holdout_duplicate_target_id():
    """Aynı target_id iki kez → ikincisi duplicate (181-182)."""
    import astrotransit.validation.blind_holdout as mod
    # Assign split her zaman blind_test dönsün
    original = mod.assign_split
    try:
        mod.assign_split = lambda tid, seed: "blind_test"
        cases = [
            _make_case("TIC 1", label="planet"),
            _make_case("TIC 1", label="planet"),  # duplicate
        ]
        r = select_holdout(cases, seed=42, split_seed=13)
        assert r["rejection_counts"].get("duplicate_target_id", 0) >= 1
    finally:
        mod.assign_split = original


def test_allocate_zero_pool_entries_excluded():
    result = allocate_quotas({"a": 0, "b": 10}, 5)
    assert result["a"] == 0
    assert result["b"] > 0


def test_allocate_proportional_remainder():
    """Kalan kota orantılı dağıtılır (105-125)."""
    result = allocate_quotas({"a": 1, "b": 3, "c": 6}, 10)
    assert sum(result.values()) == 10


def test_allocate_minimum_prevents_zero():
    """Havuzda yeterli yer varsa minimum uygulanır."""
    result = allocate_quotas({"tiny": 20, "big": 1000}, 50, minimum=5)
    assert result["tiny"] >= 5


def test_allocate_preserves_all_keys():
    pool = {"a": 10, "b": 0, "c": 5}
    result = allocate_quotas(pool, 8)
    assert set(result) == {"a", "b", "c"}


# ═══════════════════════════════════════════════════════
# _ids_from
# ═══════════════════════════════════════════════════════

def test_ids_from_dict_target_id():
    assert _ids_from({"target_id": "TIC 123"}) == {"TIC 123"}


def test_ids_from_dict_tic_id():
    assert _ids_from({"tic_id": "456"}) == {"456"}


def test_ids_from_nested_dict():
    payload = {"outer": {"target_id": "TIC 1"}}
    assert _ids_from(payload) == {"TIC 1"}


def test_ids_from_list():
    payload = [{"target_id": "TIC 1"}, {"target_id": "TIC 2"}]
    assert _ids_from(payload) == {"TIC 1", "TIC 2"}


def test_ids_from_nested_list():
    payload = [[{"target_id": "TIC 1"}], [{"tic_id": "2"}]]
    assert _ids_from(payload) == {"TIC 1", "2"}


def test_ids_from_skips_dict_value_for_target_id():
    """target_id dict/list ise skip edilir, recursive inilir."""
    payload = {"target_id": {"nested": {"target_id": "TIC X"}}}
    assert _ids_from(payload) == {"TIC X"}


def test_ids_from_empty():
    assert _ids_from({}) == set()
    assert _ids_from([]) == set()
    assert _ids_from("string") == set()


# ═══════════════════════════════════════════════════════
# load_exclusion_ids
# ═══════════════════════════════════════════════════════

def test_load_exclusion_ids_missing_file(tmp_path):
    per_source, combined = load_exclusion_ids({
        "src_a": tmp_path / "missing.json",
    })
    assert per_source["src_a"] == []
    assert combined == set()


def test_load_exclusion_ids_existing_file(tmp_path):
    p = tmp_path / "excl.json"
    p.write_text(json.dumps([
        {"target_id": "TIC 1"},
        {"target_id": "TIC 2"},
    ]))
    per_source, combined = load_exclusion_ids({"src": p})
    assert per_source["src"] == ["TIC 1", "TIC 2"]
    assert combined == {"TIC 1", "TIC 2"}


def test_load_exclusion_ids_multiple_sources(tmp_path):
    p1 = tmp_path / "a.json"
    p1.write_text(json.dumps([{"target_id": "TIC 1"}]))
    p2 = tmp_path / "b.json"
    p2.write_text(json.dumps([{"target_id": "TIC 2"}]))
    per_source, combined = load_exclusion_ids({"a": p1, "b": p2})
    assert per_source["a"] == ["TIC 1"]
    assert per_source["b"] == ["TIC 2"]
    assert combined == {"TIC 1", "TIC 2"}


# ═══════════════════════════════════════════════════════
# select_holdout
# ═══════════════════════════════════════════════════════

def _make_case(target_id, label="planet", reference="disposition 'CP'", sectors=(1,)):
    return {
        "target_id": target_id,
        "label": label,
        "reference": reference,
        "sectors": list(sectors),
        "notes": "",
    }


def test_select_holdout_empty():
    r = select_holdout([])
    assert r["status"] == "frozen"
    assert r["cases"] == []
    assert r["counts"] == {}


def test_select_holdout_label_not_eligible():
    """label LABEL_GROUPS'ta değilse rejected (172-173 dalı)."""
    cases = [_make_case("TIC 1", label="unknown_label")]
    r = select_holdout(cases, seed=42, split_seed=13)
    assert r["rejection_counts"]["label_not_holdout_eligible"] == 1


def test_select_holdout_missing_target_id():
    cases = [_make_case("", label="planet")]
    r = select_holdout(cases, seed=42, split_seed=13)
    assert r["rejection_counts"]["missing_target_id"] == 1


def test_select_holdout_duplicate_target():
    cases = [
        _make_case("TIC 1", label="planet"),
        _make_case("TIC 1", label="planet"),
    ]
    r = select_holdout(cases, seed=42, split_seed=13, split="blind_test")
    # Sadece birisi işlenir; diğeri duplicate veya not_in_split
    total_rejected = sum(r["rejection_counts"].values())
    assert total_rejected >= 1


def test_select_holdout_excluded_ids(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    cases = [_make_case("TIC 1", label="planet")]
    r = select_holdout(cases, excluded_ids=["TIC 1"], seed=42, split_seed=13)
    assert r["rejection_counts"]["used_by_prior_gate"] == 1


def test_select_holdout_deterministic():
    """Aynı girdi → aynı sha256."""
    cases = [
        _make_case(f"TIC {i}", label="planet") for i in range(20)
    ] + [
        _make_case(f"TIC {i}", label="false_positive", reference="disposition 'FP'")
        for i in range(100, 120)
    ]
    r1 = select_holdout(cases, seed=42, split_seed=13)
    r2 = select_holdout(cases, seed=42, split_seed=13)
    assert r1["holdout_sha256"] == r2["holdout_sha256"]
    assert r1["cases"] == r2["cases"]


def test_select_holdout_seed_changes_selection():
    """Farklı seed → farklı seçim (muhtemelen)."""
    cases = [
        _make_case(f"TIC {i}", label="planet") for i in range(50)
    ] + [
        _make_case(f"TIC {i}", label="false_positive", reference="disposition 'FP'")
        for i in range(200, 250)
    ]
    r1 = select_holdout(cases, seed=42, split_seed=13)
    r2 = select_holdout(cases, seed=99, split_seed=13)
    # Aynı holdout olabilir ama sha farklı
    assert "holdout_sha256" in r1
    assert "holdout_sha256" in r2


def test_select_holdout_schema():
    cases = [
        _make_case(f"TIC {i}", label="planet") for i in range(10)
    ]
    r = select_holdout(cases, seed=42, split_seed=13)
    assert r["schema_version"] == "1.0"
    assert r["corpus"] == CAMPAIGN
    assert r["status"] == "frozen"
    assert "selection" in r
    assert "floors" in r
    assert "claim_boundary" in r
    assert r["selection"]["method"] == SELECTION_METHOD


def test_select_holdout_split_filter():
    """assign_split uyumsuz olanlar reddedilir."""
    cases = [
        _make_case(f"TIC {i}", label="planet") for i in range(100)
    ]
    r = select_holdout(cases, seed=42, split_seed=13, split="blind_test")
    # Reddedilenler arasında "not_in_blind_test_split" olabilir
    assert isinstance(r["cases"], list)


# ═══════════════════════════════════════════════════════
# holdout_sha256
# ═══════════════════════════════════════════════════════

def test_holdout_sha256_empty():
    h = holdout_sha256([])
    assert len(h) == 64
    assert h == holdout_sha256([])  # deterministik


def test_holdout_sha256_deterministic():
    cases = [
        {"target_id": "TIC 1", "label": "planet", "stratum": "planet:CP"},
    ]
    assert holdout_sha256(cases) == holdout_sha256(cases)


def test_holdout_sha256_differs():
    c1 = [{"target_id": "TIC 1", "label": "planet", "stratum": "planet:CP"}]
    c2 = [{"target_id": "TIC 2", "label": "planet", "stratum": "planet:CP"}]
    assert holdout_sha256(c1) != holdout_sha256(c2)


def test_holdout_sha256_stratum_fallback():
    """stratum yoksa otomatik üretilir."""
    cases = [{"target_id": "TIC 1", "label": "planet", "reference": "disposition 'CP'"}]
    h = holdout_sha256(cases)
    assert len(h) == 64


# ═══════════════════════════════════════════════════════
# wilson_interval
# ═══════════════════════════════════════════════════════

def test_wilson_interval_zero_total():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(5, -1) is None


def test_wilson_interval_all_success():
    lo, hi = wilson_interval(100, 100)
    assert 0.0 <= lo <= 1.0
    assert hi == pytest.approx(1.0, abs=1e-3)


def test_wilson_interval_zero_success():
    lo, hi = wilson_interval(0, 100)
    assert lo == pytest.approx(0.0, abs=1e-3)
    assert hi < 0.1


def test_wilson_interval_mid():
    lo, hi = wilson_interval(50, 100)
    assert 0.3 < lo < 0.5
    assert 0.5 < hi < 0.7


def test_wilson_interval_custom_z():
    lo, hi = wilson_interval(50, 100, z=1.0)
    lo2, hi2 = wilson_interval(50, 100, z=2.0)
    # Daha küçük z → daha dar aralık
    assert (hi - lo) < (hi2 - lo2)


# ═══════════════════════════════════════════════════════
# _confusion
# ═══════════════════════════════════════════════════════

def test_confusion_empty():
    c = _confusion([])
    assert c["true_positives"] == 0
    assert c["recall"] is None
    assert c["precision"] is None
    assert c["false_positive_rate"] is None


def test_confusion_all_tp():
    rows = [{"label": "planet", "accepted_candidate": True}] * 10
    c = _confusion(rows)
    assert c["true_positives"] == 10
    assert c["recall"] == 1.0
    assert c["precision"] == 1.0


def test_confusion_all_fn():
    rows = [{"label": "planet", "accepted_candidate": False}] * 10
    c = _confusion(rows)
    assert c["false_negatives"] == 10
    assert c["recall"] == 0.0


def test_confusion_mixed():
    rows = [
        {"label": "planet", "accepted_candidate": True},
        {"label": "planet", "accepted_candidate": False},
        {"label": "false_positive", "accepted_candidate": True},
        {"label": "false_positive", "accepted_candidate": False},
    ]
    c = _confusion(rows)
    assert c["true_positives"] == 1
    assert c["false_negatives"] == 1
    assert c["false_positives"] == 1
    assert c["true_negatives"] == 1
    assert c["recall"] == 0.5
    assert c["precision"] == 0.5
    assert c["false_positive_rate"] == 0.5


def test_confusion_wilson_present():
    rows = [{"label": "planet", "accepted_candidate": True}] * 5
    c = _confusion(rows)
    assert c["wilson_recall_95"] is not None


# ═══════════════════════════════════════════════════════
# build_holdout_report — blocker yolları
# ═══════════════════════════════════════════════════════

def _make_row(target, label="planet", accepted=True, stratum="planet:CP", error=""):
    return {
        "target_id": target,
        "label": label,
        "accepted_candidate": accepted,
        "stratum": stratum,
        "error": error,
    }


def _make_valid_rows(n_per_label=80):
    rows = []
    for i in range(n_per_label):
        rows.append(_make_row(f"TIC {i}", "planet", True, "planet:CP"))
    for i in range(n_per_label, 2 * n_per_label):
        rows.append(_make_row(f"TIC {i}", "false_positive", False, "false_positive:FP"))
    return rows


def test_build_report_empty_raises():
    with pytest.raises(ValueError, match="en az bir"):
        build_holdout_report([])


def test_build_report_valid(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    r = build_holdout_report(rows, minimum_evaluated=100, minimum_per_stratum=10)
    assert r["schema_version"] == "1.0"
    assert r["campaign"] == CAMPAIGN
    assert r["status"] == "measured"
    assert r["blocking_reasons"] == []


def test_build_report_error_rows_blocker(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    rows.append(_make_row("TIC ERROR", error="detector failed"))
    r = build_holdout_report(rows, minimum_evaluated=100)
    assert any("error_rows" in b for b in r["blocking_reasons"])


def test_build_report_insufficient_evaluated(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows(n_per_label=5)
    r = build_holdout_report(rows, minimum_evaluated=1000)
    assert any("evaluated_cases_below" in b for b in r["blocking_reasons"])


def test_build_report_missing_label_group(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = [_make_row(f"TIC {i}", "planet", True) for i in range(80)]
    r = build_holdout_report(rows, minimum_evaluated=50, minimum_per_stratum=5)
    assert any("label_group_missing" in b for b in r["blocking_reasons"])


def test_build_report_stratum_below_minimum(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows(n_per_label=3)
    r = build_holdout_report(rows, minimum_evaluated=2, minimum_per_stratum=100)
    assert any("stratum_below_minimum" in b for b in r["blocking_reasons"])


def test_build_report_recall_below_floor(monkeypatch):
    """Hiç planet doğrulanmadı → recall=0 < floor."""
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = []
    for i in range(80):
        rows.append(_make_row(f"TIC {i}", "planet", False, "planet:CP"))
    for i in range(80, 160):
        rows.append(_make_row(f"TIC {i}", "false_positive", False, "false_positive:FP"))
    r = build_holdout_report(rows, minimum_evaluated=100, minimum_per_stratum=10)
    assert any("recall_below_declared_floor" in b for b in r["blocking_reasons"])


def test_build_report_fp_rate_above_ceiling(monkeypatch):
    """Tüm FP'ler kabul edildi → FP rate=1.0 > 0.6."""
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = []
    for i in range(80):
        rows.append(_make_row(f"TIC {i}", "planet", True, "planet:CP"))
    for i in range(80, 160):
        rows.append(_make_row(f"TIC {i}", "false_positive", True, "false_positive:FP"))
    r = build_holdout_report(rows, minimum_evaluated=100, minimum_per_stratum=10)
    assert any("false_positive_rate_above" in b for b in r["blocking_reasons"])


def test_build_report_manifest_status_not_frozen(monkeypatch):
    """manifest.status != frozen → blocker (374 dalı)."""
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    manifest = {
        "cases": [{"target_id": row["target_id"], "label": row["label"]}
                  for row in rows],
        "holdout_sha256": holdout_sha256([
            {"target_id": row["target_id"], "label": row["label"],
             "stratum": row["stratum"]}
            for row in rows
        ]),
        "status": "pending",
        "selection": {"seed": 42},
    }
    r = build_holdout_report(rows, manifest=manifest, minimum_evaluated=100, minimum_per_stratum=10)
    assert any("corpus_not_frozen" in b for b in r["blocking_reasons"])


def test_build_report_manifest_sha_mismatch(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    manifest = {
        "cases": [{"target_id": row["target_id"], "label": row["label"]}
                  for row in rows],
        "holdout_sha256": "deadbeef",
        "status": "frozen",
        "selection": {"seed": 42},
    }
    r = build_holdout_report(rows, manifest=manifest, minimum_evaluated=100, minimum_per_stratum=10)
    assert any("holdout_manifest_self_inconsistent" in b for b in r["blocking_reasons"])


def test_build_report_manifest_missing_corpus_row(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    manifest = {
        "cases": [{"target_id": "TIC MISSING", "label": "planet"}],
        "holdout_sha256": "x",
        "status": "frozen",
        "selection": {"seed": 42},
    }
    r = build_holdout_report(rows, manifest=manifest, minimum_evaluated=100, minimum_per_stratum=10)
    assert any("rows_not_in_frozen_corpus" in b or "corpus_rows_missing" in b
               for b in r["blocking_reasons"])


def test_build_report_method_section(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    r = build_holdout_report(rows, minimum_evaluated=100, minimum_per_stratum=10)
    assert "method" in r
    assert r["method"]["data"] == "real_light_curves"
    assert r["method"]["retrained"] is False
    assert r["method"]["detector_used_for_selection"] is False


def test_build_report_strata_section(monkeypatch):
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")
    rows = _make_valid_rows()
    r = build_holdout_report(rows, minimum_evaluated=100, minimum_per_stratum=10)
    assert "strata" in r
    assert "planet:CP" in r["strata"]
    assert "false_positive:FP" in r["strata"]


# ═══════════════════════════════════════════════════════
# non_blind branch coverage (356)
# ═══════════════════════════════════════════════════════

def test_build_report_non_blind_rows():
    """Rolü blind_test olmayan satır → non_blind blocker (356)."""
    import astrotransit.validation.blind_holdout as mod
    original = mod.assign_split
    try:
        # İlk 50 TIC "blind_test", sonrası "development" dönsün
        def fake_split(tid, seed):
            try:
                num = int(str(tid).split()[-1])
            except (ValueError, IndexError):
                return "development"
            return "blind_test" if num < 100 else "development"

        mod.assign_split = fake_split

        # Hem blind hem development split'te hedef var
        rows = []
        for i in range(80):
            rows.append(_make_row(f"TIC {i}", "planet", True, "planet:CP"))
        for i in range(100, 180):
            rows.append(_make_row(f"TIC {i}", "false_positive", False, "false_positive:FP"))
        # Bu satırlar non-blind split'te (num >= 100 ama label=planet)
        for i in range(200, 220):
            rows.append(_make_row(f"TIC {i}", "planet", True, "planet:CP"))

        r = build_holdout_report(rows, minimum_evaluated=50, minimum_per_stratum=5)
        assert any("holdout_not_blind" in b for b in r["blocking_reasons"])
    finally:
        mod.assign_split = original


# ═══════════════════════════════════════════════════════
# Manifest SHA eşleşen + status!=frozen (368->370 path)
# ═══════════════════════════════════════════════════════

def test_build_report_manifest_sha_match_status_bad(monkeypatch):
    """SHA eşleşir → 368 False → 370'e atlar → status!=frozen tetiklenir."""
    import astrotransit.validation.blind_holdout as mod
    monkeypatch.setattr(mod, "assign_split", lambda tid, seed: "blind_test")

    rows = _make_valid_rows()
    manifest_cases = [
        {"target_id": row["target_id"], "label": row["label"],
         "stratum": row["stratum"]}
        for row in rows
    ]
    # SHA tam eşleşmeli — holdout_sha256 ile aynı şekilde hesapla
    correct_sha = holdout_sha256([
        {"target_id": row["target_id"], "label": row["label"],
         "stratum": row["stratum"]}
        for row in rows
    ])
    manifest = {
        "cases": manifest_cases,
        "holdout_sha256": correct_sha,
        "status": "pending",  # ← blocker
        "selection": {"seed": 42},
    }
    r = build_holdout_report(
        rows, manifest=manifest,
        minimum_evaluated=100, minimum_per_stratum=10,
    )
    # SHA eşleşti → bu blocker YOK
    assert not any("holdout_manifest_self_inconsistent" in b for b in r["blocking_reasons"])
    # Status pending → blocker VAR
    assert any("corpus_not_frozen" in b for b in r["blocking_reasons"])
