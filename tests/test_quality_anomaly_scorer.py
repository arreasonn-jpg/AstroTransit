"""
AnomalyScorer birim testleri.

Strateji
--------
ResidualReport, TransitConsistencyReport ve TimingReport MagicMock
ile mock'lanir; gercek raporlara ihtiyac yok. Boylece scorer
orkestrasyonu izole test edilir.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from astrotransit.quality.anomaly_scorer import (
    AnomalyComponent,
    AnomalyReport,
    AnomalyScorer,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def scorer() -> AnomalyScorer:
    return AnomalyScorer()


def _residual(target: str = "TIC-100", sector: int = 1, flag: str = "CLEAN", score: float = 0.1):
    r = MagicMock()
    r.target_id = target
    r.sector = sector
    r.flag = flag
    r.score = score
    r.summary.return_value = {"flag": flag, "score": score}
    return r


def _transit(target: str = "TIC-100", sector: int = 1, flag: str = "CONSISTENT", score: float = 0.1):
    r = MagicMock()
    r.target_id = target
    r.sector = sector
    r.flag = flag
    r.score = score
    r.summary.return_value = f"{target} S{sector} flag={flag}"
    return r


def _timing(target: str = "TIC-100", sector: int = 1, flag: str = "STABLE", score: float = 0.1):
    r = MagicMock()
    r.target_id = target
    r.sector = sector
    r.flag = flag
    r.score = score
    r.summary.return_value = f"{target} S{sector} flag={flag}"
    return r


# ─────────────────────────────────────────────────────────────
# AnomalyComponent
# ─────────────────────────────────────────────────────────────

def test_component_defaults() -> None:
    c = AnomalyComponent(name="residual", available=True, weight=0.35)
    assert c.score is None
    assert c.flag == "MISSING"
    assert c.severe is False
    assert c.moderate is False


def test_component_to_dict() -> None:
    c = AnomalyComponent(
        name="residual", available=True, weight=0.35,
        score=0.42, flag="SUSPECT", severe=False, moderate=True,
    )
    d = c.to_dict()
    assert d["name"] == "residual"
    assert d["available"] is True
    assert d["weight"] == 0.35
    assert d["score"] == 0.42
    assert d["flag"] == "SUSPECT"
    assert d["moderate"] is True


def test_component_to_dict_none_score() -> None:
    c = AnomalyComponent(name="x", available=False, weight=0.5)
    d = c.to_dict()
    assert d["score"] is None


# ─────────────────────────────────────────────────────────────
# AnomalyReport
# ─────────────────────────────────────────────────────────────

def test_report_defaults() -> None:
    r = AnomalyReport(target_id="TIC-1", sector=1)
    assert r.anomaly_score == 0.0
    assert r.anomaly_flag == "UNKNOWN"
    assert r.recommended_action == "none"
    assert r.components == []
    assert r.n_available == 0


def test_report_to_dict() -> None:
    r = AnomalyReport(
        target_id="TIC-1", sector=1,
        anomaly_score=0.42, anomaly_flag="REVIEW",
        recommended_action="manual_vetting_review",
        components=[
            AnomalyComponent("residual", True, 0.35, 0.5, "SUSPECT", False, True),
        ],
        n_available=1, n_severe=0, n_moderate=1,
        details={"anomaly_score": 0.42},
    )
    d = r.to_dict()
    assert d["target_id"] == "TIC-1"
    assert d["anomaly_score"] == 0.42
    assert d["anomaly_flag"] == "REVIEW"
    assert d["n_moderate"] == 1
    assert len(d["components"]) == 1


def test_report_summary() -> None:
    r = AnomalyReport(
        target_id="TIC-1", sector=3,
        anomaly_score=0.5, anomaly_flag="REVIEW",
        recommended_action="manual_vetting_review",
        n_available=2, n_severe=0, n_moderate=1,
    )
    s = r.summary()
    assert "TIC-1" in s
    assert "S3" in s
    assert "REVIEW" in s
    assert "manual_vetting_review" in s


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_scorer_init_defaults() -> None:
    s = AnomalyScorer()
    assert s.residual_weight == 0.35
    assert s.transit_weight == 0.40
    assert s.timing_weight == 0.25


def test_scorer_init_custom_weights() -> None:
    s = AnomalyScorer(residual_weight=0.5, transit_weight=0.3, timing_weight=0.2)
    assert s.residual_weight == 0.5
    assert s.transit_weight == 0.3
    assert s.timing_weight == 0.2


# ─────────────────────────────────────────────────────────────
# _resolve_identity
# ─────────────────────────────────────────────────────────────

def test_resolve_identity_no_reports() -> None:
    target, sector = AnomalyScorer._resolve_identity(None, None, None)
    assert target == "UNKNOWN_TARGET"
    assert sector == -1


def test_resolve_identity_one_report() -> None:
    target, sector = AnomalyScorer._resolve_identity(_residual(), None, None)
    assert target == "TIC-100"
    assert sector == 1


def test_resolve_identity_consistent_reports() -> None:
    target, sector = AnomalyScorer._resolve_identity(
        _residual(), _transit(), _timing(),
    )
    assert target == "TIC-100"
    assert sector == 1


def test_resolve_identity_mismatch_uses_first() -> None:
    target, sector = AnomalyScorer._resolve_identity(
        _residual("TIC-100", 1),
        _transit("TIC-999", 5),  # farkli
        None,
    )
    assert target == "TIC-100"
    assert sector == 1


# ─────────────────────────────────────────────────────────────
# _build_residual_component
# ─────────────────────────────────────────────────────────────

def test_build_residual_missing(scorer: AnomalyScorer) -> None:
    c = scorer._build_residual_component(None)
    assert c.available is False
    assert c.flag == "MISSING"
    assert c.score is None


def test_build_residual_clean(scorer: AnomalyScorer) -> None:
    c = scorer._build_residual_component(_residual(flag="CLEAN", score=0.1))
    assert c.available is True
    assert c.flag == "CLEAN"
    assert c.severe is False
    assert c.moderate is False


def test_build_residual_anomalous(scorer: AnomalyScorer) -> None:
    c = scorer._build_residual_component(_residual(flag="ANOMALOUS", score=0.9))
    assert c.severe is True


def test_build_residual_suspect(scorer: AnomalyScorer) -> None:
    c = scorer._build_residual_component(_residual(flag="SUSPECT", score=0.5))
    assert c.moderate is True
    assert c.severe is False


# ─────────────────────────────────────────────────────────────
# _build_transit_component
# ─────────────────────────────────────────────────────────────

def test_build_transit_missing(scorer: AnomalyScorer) -> None:
    c = scorer._build_transit_component(None)
    assert c.available is False


def test_build_transit_consistent(scorer: AnomalyScorer) -> None:
    c = scorer._build_transit_component(_transit(flag="CONSISTENT", score=0.1))
    assert c.flag == "CONSISTENT"
    assert c.severe is False
    assert c.moderate is False


def test_build_transit_eb_suspect(scorer: AnomalyScorer) -> None:
    c = scorer._build_transit_component(_transit(flag="EB_SUSPECT", score=0.8))
    assert c.severe is True


def test_build_transit_variable(scorer: AnomalyScorer) -> None:
    c = scorer._build_transit_component(_transit(flag="VARIABLE", score=0.4))
    assert c.moderate is True


# ─────────────────────────────────────────────────────────────
# _build_timing_component
# ─────────────────────────────────────────────────────────────

def test_build_timing_missing(scorer: AnomalyScorer) -> None:
    c = scorer._build_timing_component(None)
    assert c.available is False


def test_build_timing_stable(scorer: AnomalyScorer) -> None:
    c = scorer._build_timing_component(_timing(flag="STABLE", score=0.1))
    assert c.severe is False
    assert c.moderate is False


def test_build_timing_unstable(scorer: AnomalyScorer) -> None:
    c = scorer._build_timing_component(_timing(flag="TIMING_UNSTABLE", score=0.8))
    assert c.severe is True


def test_build_timing_ttv_candidate(scorer: AnomalyScorer) -> None:
    c = scorer._build_timing_component(_timing(flag="TTV_CANDIDATE", score=0.4))
    assert c.moderate is True


# ─────────────────────────────────────────────────────────────
# _compute_weighted_score
# ─────────────────────────────────────────────────────────────

def test_weighted_score_no_active() -> None:
    components = [
        AnomalyComponent("a", False, 0.5),
        AnomalyComponent("b", False, 0.5),
    ]
    assert AnomalyScorer._compute_weighted_score(components) == 0.0


def test_weighted_score_single_active() -> None:
    components = [
        AnomalyComponent("a", True, 0.35, 0.8),
    ]
    # 0.35*0.8 / 0.35 = 0.8 (floating point toleransli)
    assert AnomalyScorer._compute_weighted_score(components) == pytest.approx(0.8)


def test_weighted_score_two_active() -> None:
    components = [
        AnomalyComponent("a", True, 0.5, 0.8),
        AnomalyComponent("b", True, 0.5, 0.2),
    ]
    assert AnomalyScorer._compute_weighted_score(components) == pytest.approx(0.5)


def test_weighted_score_unequal_weights() -> None:
    """Agirlikli ortalama: (0.7*0.8 + 0.3*0.2) / 1.0 = 0.62."""
    components = [
        AnomalyComponent("a", True, 0.7, 0.8),
        AnomalyComponent("b", True, 0.3, 0.2),
    ]
    assert AnomalyScorer._compute_weighted_score(components) == pytest.approx(0.62)


def test_weighted_score_clipped() -> None:
    components = [AnomalyComponent("a", True, 0.5, 1.5)]
    assert AnomalyScorer._compute_weighted_score(components) == 1.0


# ─────────────────────────────────────────────────────────────
# _compute_flag
# ─────────────────────────────────────────────────────────────

def test_flag_no_available() -> None:
    components = [AnomalyComponent("a", False, 0.5)]
    assert AnomalyScorer._compute_flag(components, 0.0) == "UNKNOWN"


def test_flag_clean() -> None:
    components = [AnomalyComponent("a", True, 0.5, 0.1)]
    assert AnomalyScorer._compute_flag(components, 0.1) == "CLEAN"


def test_flag_review_score_threshold() -> None:
    components = [AnomalyComponent("a", True, 0.5, 0.3)]
    assert AnomalyScorer._compute_flag(components, 0.3) == "REVIEW"


def test_flag_reject_high_score() -> None:
    components = [AnomalyComponent("a", True, 0.5, 0.7)]
    assert AnomalyScorer._compute_flag(components, 0.7) == "REJECT"


def test_flag_reject_two_severe() -> None:
    components = [
        AnomalyComponent("a", True, 0.5, 0.5, "ANOMALOUS", True),
        AnomalyComponent("b", True, 0.5, 0.5, "X", True),
    ]
    assert AnomalyScorer._compute_flag(components, 0.5) == "REJECT"


def test_flag_reject_transit_severe() -> None:
    """transit_consistency severe -> REJECT."""
    components = [
        AnomalyComponent("transit_consistency", True, 0.5, 0.5, "EB_SUSPECT", True),
    ]
    assert AnomalyScorer._compute_flag(components, 0.4) == "REJECT"


def test_flag_review_one_severe() -> None:
    components = [AnomalyComponent("a", True, 0.5, 0.4, "X", True)]
    assert AnomalyScorer._compute_flag(components, 0.3) == "REVIEW"


def test_flag_review_one_moderate() -> None:
    components = [AnomalyComponent("a", True, 0.5, 0.2, "Y", False, True)]
    assert AnomalyScorer._compute_flag(components, 0.2) == "REVIEW"


# ─────────────────────────────────────────────────────────────
# _recommend_action
# ─────────────────────────────────────────────────────────────

def test_action_clean() -> None:
    assert AnomalyScorer._recommend_action("CLEAN", []) == "proceed_to_followup"


def test_action_unknown() -> None:
    assert AnomalyScorer._recommend_action("UNKNOWN", []) == "insufficient_data"


def test_action_reject() -> None:
    assert AnomalyScorer._recommend_action("REJECT", []) == "deprioritize_or_reinspect"


def test_action_review_timing() -> None:
    components = [AnomalyComponent("timing", True, 0.5, 0.4, "X", True)]
    assert AnomalyScorer._recommend_action("REVIEW", components) == "manual_timing_review"


def test_action_review_residual() -> None:
    components = [AnomalyComponent("residual", True, 0.5, 0.4, "SUSPECT", False, True)]
    assert AnomalyScorer._recommend_action("REVIEW", components) == "inspect_residuals_and_folded_transit"


def test_action_review_generic() -> None:
    components = [AnomalyComponent("other", True, 0.5, 0.4, "X", False, True)]
    assert AnomalyScorer._recommend_action("REVIEW", components) == "manual_vetting_review"


# ─────────────────────────────────────────────────────────────
# score() — entegrasyon
# ─────────────────────────────────────────────────────────────

def test_score_no_reports(scorer: AnomalyScorer) -> None:
    report = scorer.score()
    assert isinstance(report, AnomalyReport)
    assert report.target_id == "UNKNOWN_TARGET"
    assert report.sector == -1
    assert report.anomaly_flag == "UNKNOWN"
    assert report.n_available == 0


def test_score_all_clean(scorer: AnomalyScorer) -> None:
    report = scorer.score(
        residual_report=_residual(flag="CLEAN", score=0.1),
        transit_report=_transit(flag="CONSISTENT", score=0.1),
        timing_report=_timing(flag="STABLE", score=0.1),
    )
    assert report.anomaly_flag == "CLEAN"
    assert report.recommended_action == "proceed_to_followup"
    assert report.n_available == 3
    assert report.n_severe == 0


def test_score_reject(scorer: AnomalyScorer) -> None:
    report = scorer.score(
        residual_report=_residual(flag="ANOMALOUS", score=0.9),
        transit_report=_transit(flag="EB_SUSPECT", score=0.8),
        timing_report=_timing(flag="TIMING_UNSTABLE", score=0.8),
    )
    assert report.anomaly_flag == "REJECT"
    assert report.n_severe >= 2


def test_score_review(scorer: AnomalyScorer) -> None:
    report = scorer.score(
        residual_report=_residual(flag="SUSPECT", score=0.5),
        transit_report=_transit(flag="VARIABLE", score=0.3),
        timing_report=None,
    )
    assert report.anomaly_flag == "REVIEW"


def test_score_partial_reports(scorer: AnomalyScorer) -> None:
    """Sadece residual verilirse n_available=1."""
    report = scorer.score(residual_report=_residual(flag="CLEAN", score=0.1))
    assert report.n_available == 1


def test_score_details_present(scorer: AnomalyScorer) -> None:
    report = scorer.score(
        residual_report=_residual(),
        transit_report=_transit(),
    )
    assert "anomaly_score" in report.details
    assert "weights" in report.details
    assert "component_flags" in report.details
    assert "component_scores" in report.details
    assert "residual_summary" in report.details
    assert "transit_summary" in report.details


def test_score_custom_weights(monkeypatch) -> None:
    s = AnomalyScorer(residual_weight=0.5, transit_weight=0.5, timing_weight=0.0)
    report = s.score(
        residual_report=_residual(flag="ANOMALOUS", score=1.0),
        transit_report=_transit(flag="CONSISTENT", score=0.0),
    )
    # (1.0*0.5 + 0.0*0.5) / 1.0 = 0.5
    assert report.anomaly_score == pytest.approx(0.5)
