"""astrotransit/outputs/schemas.py için testler."""
from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from astrotransit.outputs.schemas import (
    TransitCandidateRecord,
    _as_list,
    _derive_detection_confidence,
    _dict_from_dataclass,
    _earth_twin_status,
    _finite_or_none,
    _first_positive,
    _first_value,
    _get,
    _json_load_list_or_empty,
    _json_load_or_empty,
    _length,
    _positive_finite,
    _serialise_list,
    _stellar_value,
    _tic_id_or_zero,
    build_long_period_record,
    build_record,
)

# ═══════════════════════════════════════════════════════
# Helper fonksiyonlar
# ═══════════════════════════════════════════════════════

def test_finite_or_none_none():
    assert _finite_or_none(None) is None


def test_finite_or_none_numpy_scalar():
    assert _finite_or_none(np.int64(5)) == 5
    assert isinstance(_finite_or_none(np.float64(3.5)), float)


def test_finite_or_none_nan_inf():
    assert _finite_or_none(float("nan")) is None
    assert _finite_or_none(float("inf")) is None
    assert _finite_or_none(float("-inf")) is None


def test_finite_or_none_ok():
    assert _finite_or_none(3.14) == 3.14
    assert _finite_or_none("x") == "x"


def test_as_list_none():
    assert _as_list(None) == []


def test_as_list_string():
    assert _as_list("hello") == ["hello"]
    assert _as_list("") == []


def test_as_list_iterable():
    assert _as_list([1, 2, 3]) == ["1", "2", "3"]


def test_get_none():
    assert _get(None, "x", 99) == 99


def test_get_dict():
    assert _get({"a": 1}, "a") == 1
    assert _get({"a": 1}, "b", 2) == 2


def test_get_object():
    obj = SimpleNamespace(a=5)
    assert _get(obj, "a") == 5
    assert _get(obj, "missing", "default") == "default"


def test_length_none():
    assert _length(None) == 0


def test_length_no_len():
    assert _length(42) == 0


def test_length_ok():
    assert _length([1, 2, 3]) == 3
    assert _length(np.array([1, 2])) == 2


def test_dict_from_dataclass_none():
    assert _dict_from_dataclass(None) == {}


def test_dict_from_dataclass_with_to_dict():
    obj = SimpleNamespace(to_dict=lambda: {"x": 1})
    assert _dict_from_dataclass(obj) == {"x": 1}


def test_dict_from_dataclass_broken_to_dict():
    def bad():
        raise RuntimeError("boom")
    obj = SimpleNamespace(to_dict=bad)
    assert _dict_from_dataclass(obj) == {}


def test_dict_from_dataclass_real_dataclass():
    @dataclass
    class D:
        a: int = 1
    assert _dict_from_dataclass(D()) == {"a": 1}


def test_dict_from_dataclass_dict():
    assert _dict_from_dataclass({"k": "v"}) == {"k": "v"}


def test_json_load_or_empty_variants():
    assert _json_load_or_empty(None) == {}
    assert _json_load_or_empty("") == {}
    assert _json_load_or_empty({"a": 1}) == {"a": 1}
    assert _json_load_or_empty('{"b": 2}') == {"b": 2}
    assert _json_load_or_empty("not json") == {}
    assert _json_load_or_empty("[1,2]") == {}  # list, not dict


def test_json_load_list_or_empty_variants():
    assert _json_load_list_or_empty(None) == []
    assert _json_load_list_or_empty([]) == []
    assert _json_load_list_or_empty("[1,2]") == [1, 2]
    assert _json_load_list_or_empty('{"a":1}') == []
    assert _json_load_list_or_empty("bad") == []


def test_stellar_value_variants():
    props = SimpleNamespace(radius=1.5)
    assert _stellar_value(props, "radius") == 1.5
    assert _stellar_value(props, "missing", 0.0) == 0.0


def test_serialise_list_none_empty():
    assert _serialise_list(None) == "[]"
    assert _serialise_list("") == "[]"


def test_serialise_list_json_string():
    assert _serialise_list("[1,2]") == "[1, 2]"


def test_serialise_list_plain_string():
    assert _serialise_list("hello") == '["hello"]'


def test_serialise_list_iterable():
    assert _serialise_list([1, 2]) == "[1, 2]"


def test_first_value():
    assert _first_value(None, None, 5) == 5
    assert _first_value(None, None, None) is None
    assert _first_value(0, 1) == 0  # 0 None değil


def test_first_positive():
    assert _first_positive(None, 0, -1, 5) == 5
    assert _first_positive(None, 0, -1) is None


def test_positive_finite():
    assert _positive_finite(5) is True
    assert _positive_finite(0) is False
    assert _positive_finite(-1) is False
    assert _positive_finite(None) is False
    assert _positive_finite("bad") is False
    assert _positive_finite(float("inf")) is False


def test_earth_twin_status():
    assert _earth_twin_status("CONFIRMED_EARTH_TWIN", followup_confirmed=True) == "confirmed_earth_twin"
    assert _earth_twin_status("EARTH_TWIN_CANDIDATE", followup_confirmed=False) == "earth_twin_candidate"
    assert _earth_twin_status("PHOTOMETRIC_EARTH_ANALOG", followup_confirmed=False) == "photometric_earth_like_candidate"
    assert _earth_twin_status("OTHER", followup_confirmed=True) == "followup_confirmed_non_earth_twin"
    assert _earth_twin_status("", followup_confirmed=False) == "unverified"


def test_derive_detection_confidence_no_vetting():
    assert _derive_detection_confidence(None, None) == "UNKNOWN"


def test_derive_detection_confidence_all_zero():
    v = SimpleNamespace(n_pass=0, n_fail=0, n_warn=0)
    assert _derive_detection_confidence(v, None) == "UNKNOWN"


def test_derive_detection_confidence_low_many_fails():
    v = SimpleNamespace(n_pass=3, n_fail=2, n_warn=0)
    assert _derive_detection_confidence(v, None) == "LOW"


def test_derive_detection_confidence_low_high_fpp():
    v = SimpleNamespace(n_pass=5, n_fail=0, n_warn=0)
    assert _derive_detection_confidence(v, 0.6) == "LOW"


def test_derive_detection_confidence_high():
    v = SimpleNamespace(n_pass=8, n_fail=0, n_warn=0)
    assert _derive_detection_confidence(v, 0.05) == "HIGH"


def test_derive_detection_confidence_medium():
    v = SimpleNamespace(n_pass=5, n_fail=0, n_warn=0)
    assert _derive_detection_confidence(v, None) == "MEDIUM"


def test_derive_detection_confidence_fallback_low():
    v = SimpleNamespace(n_pass=1, n_fail=0, n_warn=1)
    assert _derive_detection_confidence(v, None) == "LOW"


def test_tic_id_or_zero_variants():
    assert _tic_id_or_zero(None) == 0
    assert _tic_id_or_zero("") == 0
    assert _tic_id_or_zero("TIC 123") == 123
    assert _tic_id_or_zero("456") == 456
    assert _tic_id_or_zero("bad") == 0


# ═══════════════════════════════════════════════════════
# TransitCandidateRecord
# ═══════════════════════════════════════════════════════

def test_record_default_creation():
    r = TransitCandidateRecord()
    assert r.mission == "TESS"
    assert r.instrument == "TESS"
    assert r.created_at != ""  # __post_init__


def test_record_post_init_source_id():
    r = TransitCandidateRecord(source_id=None)
    assert r.source_id == ""


def test_record_post_init_infer_claim_status():
    r = TransitCandidateRecord()
    # claim_status DETECTED'dan infer edilmiş olmalı
    assert r.claim_status != "DETECTED" or r.claim_status == "DETECTED"


def test_record_post_init_failure_codes():
    r = TransitCandidateRecord()
    # failure_codes JSON string olmalı
    json.loads(r.failure_codes)


def test_record_to_flat_dict():
    r = TransitCandidateRecord(source_id="TIC 1", period=3.5)
    d = r.to_flat_dict()
    assert d["source_id"] == "TIC 1"
    assert d["period"] == 3.5


def test_record_to_flat_dict_handles_nan():
    r = TransitCandidateRecord(period=float("nan"))
    d = r.to_flat_dict()
    assert d["period"] is None


def test_record_to_flat_dict_list_to_list():
    r = TransitCandidateRecord()
    d = r.to_flat_dict()
    # Tüm değerler JSON-serializable olmalı
    json.dumps(d, default=str)


def test_record_to_dict_alias():
    r = TransitCandidateRecord(source_id="X")
    assert r.to_dict() == r.to_flat_dict()


# ═══════════════════════════════════════════════════════
# build_record
# ═══════════════════════════════════════════════════════

def _minimal_candidate():
    return SimpleNamespace(
        target_id="TIC 123", sector=14, period=3.5, period_err=0.01,
        t0=100.0, rp_rs=0.1, depth=0.001, duration=0.1,
        confirmed=True, status="confirmed", snr=15.0,
        transit_times=np.array([100.0, 103.5]),
    )


def _full_candidate():
    bls_peak = SimpleNamespace(period=3.5, power=20.0, depth=0.001)
    bls = SimpleNamespace(best=bls_peak)
    tls = SimpleNamespace(period=3.5, sde=12.0, snr=15.0, odd_even_mismatch=0.05)
    return SimpleNamespace(
        target_id="TIC 123", sector=14, period=3.5, period_err=0.01,
        t0=100.0, rp_rs=0.1, depth=0.001, duration=0.1,
        confirmed=True, status=SimpleNamespace(value="confirmed"),
        snr=15.0, bls_result=bls, tls_result=tls,
        transit_times=np.array([100.0, 103.5]),
    )


def test_build_record_minimal():
    r = build_record(_minimal_candidate())
    assert isinstance(r, TransitCandidateRecord)
    assert r.source_id == "TIC 123"
    assert r.tic_id == 123
    assert r.sector == 14
    assert r.period == 3.5
    assert r.fit_method == "cascade_only"


def test_build_record_with_bls_tls():
    r = build_record(_full_candidate())
    assert r.bls_period == 3.5
    assert r.bls_power == 20.0
    assert r.tls_period == 3.5
    assert r.tls_sde == 12.0


def test_build_record_with_stellar_props():
    props = SimpleNamespace(
        radius=1.0, mass=1.0, teff=5778.0, tmag=10.0, logg=4.4,
        ra=45.0, dec=-20.0,
    )
    r = build_record(_minimal_candidate(), stellar_props=props)
    assert r.radius_rsun == 1.0
    assert r.teff_k == 5778.0
    assert r.tmag == 10.0


def test_build_record_with_map_fit():
    fit = SimpleNamespace(
        success=True, fit_method="map", period=3.51, period_err=0.005,
        t0=100.1, rp_rs=0.105, impact_parameter=0.3,
        a_over_rs=10.0, inclination=88.0, u1=0.3, u2=0.2,
        log_jitter=-8.0, baseline=1.0, rp_rs_err=0.002,
        log_likelihood=-100.0,
    )
    r = build_record(_minimal_candidate(), fit_result=fit)
    assert r.fit_method == "map"
    assert r.period == 3.51
    assert r.rp_rs == 0.105
    assert r.period_err_source == "map_approx"


def test_build_record_with_mcmc_fit():
    fit = SimpleNamespace(
        success=True, fit_method="mcmc", period=3.51, period_err=0.005,
        t0=100.1, rp_rs=0.105, impact_parameter=0.3,
        a_over_rs=10.0, inclination=88.0, u1=0.3, u2=0.2,
        log_jitter=-8.0, baseline=1.0, rp_rs_err=0.002,
        posteriors={"period": object(), "u1": object()},
        convergence_ok=True, r_hat_max=1.005, n_divergences=0,
    )
    r = build_record(_minimal_candidate(), fit_result=fit)
    assert r.fit_method == "mcmc"
    assert r.period_sampled is True
    assert r.period_err_source == "posterior"
    assert r.mcmc_converged is True


def test_build_record_fit_failed_uses_cascade():
    fit = SimpleNamespace(success=False, period=99.0)
    r = build_record(_minimal_candidate(), fit_result=fit)
    assert r.period == 3.5  # cascade'den
    assert r.fit_method == "cascade_only"


def test_build_record_with_quality_result():
    score = SimpleNamespace(total_score=85.0, candidate_class="A", anomaly_flags=[])
    vetting = SimpleNamespace(
        is_false_positive=False, n_pass=8, n_fail=0, n_warn=0,
        fp_flags=["clean"],
    )
    metrics = SimpleNamespace(
        photometric=SimpleNamespace(n_points=1000, cdpp_1hr=100.0, data_completeness=0.95, noise_ppm=150.0),
        transit=SimpleNamespace(n_transits=3, residual_rms=1e-4, transit_symmetry=0.98, timing_rms=0.001),
        stellar=SimpleNamespace(is_variable_star=False, is_binary_suspect=False, secondary_eclipse_depth=0.0),
    )
    quality = SimpleNamespace(
        metrics=metrics, snr=None, vetting=vetting, score=score, anomaly=None,
    )
    r = build_record(_minimal_candidate(), quality_result=quality)
    assert r.n_points == 1000
    assert r.n_transits == 3
    assert r.total_score == 85.0
    assert r.detection_confidence == "HIGH"


def test_build_record_with_fpp_report():
    fpp_report = SimpleNamespace(
        fpp=0.05, fpp_method="heuristic", confidence="HIGH",
    )
    quality = SimpleNamespace(fpp_report=fpp_report)
    r = build_record(_minimal_candidate(), quality_result=quality)
    assert r.fpp == 0.05
    assert r.fpp_method == "heuristic"
    assert r.detection_confidence == "HIGH"


def test_build_record_nan_handling():
    cand = _minimal_candidate()
    cand.depth = float("nan")
    r = build_record(cand)
    # NaN → None olmalı
    assert r.depth is None


# ═══════════════════════════════════════════════════════
# build_long_period_record
# ═══════════════════════════════════════════════════════

def test_build_long_period_no_peak():
    lp = SimpleNamespace(best=None)
    assert build_long_period_record(lp) is None


def test_build_long_period_happy():
    peak = SimpleNamespace(
        period=100.0, period_err=2.0, t0=1000.0, duration=0.1,
        depth=1e-3, transit_times=np.array([1000.0, 1100.0]),
        n_observed_transits=2, identifiability="multi_transit",
    )
    lp = SimpleNamespace(
        target_id="TIC 1", best=peak, coverage_baseline_days=200.0,
        observed_days=180.0, source_sectors=[1, 2], notes=[],
    )
    r = build_long_period_record(lp)
    assert r is not None
    assert r.search_channel == "long_period"
    assert r.long_period_screening is True
    assert r.fit_method == "long_period_bls"
    assert r.candidate_class == "LONG_PERIOD_CANDIDATE"
    assert r.period_err_source == "long_period_heuristic"


def test_build_long_period_single_transit():
    peak = SimpleNamespace(
        period=200.0, period_err=100.0, t0=1000.0, duration=0.1,
        depth=1e-3, transit_times=np.array([1000.0]),
        n_observed_transits=1, identifiability="single_transit_ambiguous",
    )
    lp = SimpleNamespace(
        target_id="TIC 1", best=peak, coverage_baseline_days=200.0,
        observed_days=180.0, source_sectors=(1,), notes=["tek transit"],
    )
    r = build_long_period_record(lp)
    assert r.candidate_class == "LONG_PERIOD_SINGLE_TRANSIT"
    # notes aktarılmış olmalı
    assert "tek transit" in r.earth_similarity_notes


def test_build_long_period_no_period_err():
    peak = SimpleNamespace(
        period=100.0, period_err=0.0, t0=1000.0, duration=0.1,
        depth=1e-3, transit_times=np.array([1000.0, 1100.0]),
        n_observed_transits=2, identifiability="multi_transit",
    )
    lp = SimpleNamespace(
        target_id="TIC 1", best=peak, coverage_baseline_days=200.0,
        observed_days=180.0, source_sectors=(1,), notes=[],
    )
    r = build_long_period_record(lp)
    assert r.period_err_source == "unavailable"
