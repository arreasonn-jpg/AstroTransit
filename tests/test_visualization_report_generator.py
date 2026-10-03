"""
VisualizationReportGenerator birim testleri.

Kapsam
------
- VisualizationReport.to_dict
- generate(): save_figures False/True
- Tüm opsiyonel parametreler var/yok kombinasyonlari
- Hata yakalama (alt plotter exception)
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.detection.bls_search import BLSPeak, BLSResult
from astrotransit.detection.cascade import CascadeCandidate, CascadeStatus
from astrotransit.detection.tls_search import TLSResult
from astrotransit.modeling.map_fit import MAPFitResult
from astrotransit.modeling.parameters import DerivedParameters
from astrotransit.preprocessing.normalization import NormalizedLightCurve
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.quality.scorer import (
    CandidateClass,
    QualityScore,
    ScoreComponent,
)
from astrotransit.quality.vetting import (
    VettingReport,
    VettingTest,
    VettingVerdict,
)
from astrotransit.settings import GeneralConfig, OutputsConfig, Settings
from astrotransit.visualization.report_generator import (
    VisualizationReport,
    VisualizationReportGenerator,
)


@pytest.fixture(autouse=True)
def _close_figures():
    yield
    plt.close("all")


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

def _settings(tmp_path: Path, save_figures: bool = True) -> Settings:
    return Settings(
        general=GeneralConfig(
            output_dir=str(tmp_path / "outputs"),
            temp_dir=str(tmp_path / "tmp"),
        ),
        outputs=OutputsConfig(
            save_figures=save_figures,
            figure_format="png",
            figure_dpi=72,
        ),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return _settings(tmp_path)


@pytest.fixture
def generator(tmp_path: Path) -> VisualizationReportGenerator:
    return VisualizationReportGenerator(settings=_settings(tmp_path))


def _detrended(target: str = "TIC-100", sector: int = 1, n: int = 200) -> DetrendedLightCurve:
    rng = np.random.default_rng(0)
    t = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 1e-3, size=n)
    err = np.full(n, 1e-3)
    trend = np.ones(n)
    raw = flux + 0.01
    return DetrendedLightCurve(
        target_id=target,
        sector=sector,
        time=t,
        flux=flux,
        flux_err=err,
        trend=trend,
        raw_flux=raw,
        method="biweight",
        window_length=0.5,
        break_tolerance=0.5,
        meta={"CADENCE": "120s"},
    )


def _normalized(target: str = "TIC-100", sector: int = 1, n: int = 200) -> NormalizedLightCurve:
    rng = np.random.default_rng(0)
    t = np.linspace(100.0, 120.0, n)
    flux = 1.0 + rng.normal(0, 1e-3, size=n)
    err = np.full(n, 1e-3)
    return NormalizedLightCurve(
        target_id=target,
        sector=sector,
        time=t,
        flux=flux,
        flux_err=err,
        norm_factor=1.0,
        method="median",
        meta={},
    )


def _candidate(target: str = "TIC-100", sector: int = 1, n_transits: int = 5) -> CascadeCandidate:
    dummy_bls = type("BLSDummy", (), {})()
    return CascadeCandidate(
        target_id=target,
        sector=sector,
        status=CascadeStatus.CONFIRMED,
        confirmed=True,
        bls_result=dummy_bls,  # type: ignore[arg-type]
        tls_result=None,
        period=5.0,
        period_err=0.01,
        t0=100.0,
        duration=0.15,
        depth=0.005,
        rp_rs=0.08,
        snr=8.0,
        sde=9.5,
        transit_times=np.linspace(100.0, 120.0, n_transits),
        decision_log=[],
    )


def _bls_result(target: str = "TIC-100", sector: int = 1) -> BLSResult:
    periods = np.logspace(np.log10(0.5), np.log10(20.0), 200)
    power = 5.0 + 8.0 * np.exp(-0.5 * ((np.log10(periods) - np.log10(5.0)) / 0.1) ** 2)
    best = BLSPeak(
        period=5.0, period_err=0.01, duration=0.15, depth=0.005,
        t0=1.0, power=12.5, snr=8.0, depth_err=0.001, n_transits=4,
        transit_times=np.linspace(0.0, 20.0, 4),
    )
    return BLSResult(
        target_id=target, sector=sector, best=best, all_peaks=[best],
        periods_searched=periods, power_array=power,
        n_periods_searched=len(periods), has_candidate=True,
    )


def _tls_result(target: str = "TIC-100", sector: int = 1) -> TLSResult:
    phase = np.linspace(0.0, 1.0, 200)
    flux = 1.0 + np.random.default_rng(0).normal(0, 1e-3, size=200)
    model_phase = np.linspace(0.0, 1.0, 300)
    model_flux = np.ones(300)
    return TLSResult(
        target_id=target, sector=sector, period=5.0, period_err=0.001,
        t0=100.0, duration=0.15, depth=0.005, rp_rs=0.08,
        sde=9.5, snr=8.0, odd_even_mismatch=0.5, transit_count=4,
        transit_times=np.linspace(100.0, 120.0, 4),
        transit_depths=np.full(4, 0.005),
        folded_phase=phase, folded_flux=flux,
        model_phase=model_phase, model_flux=model_flux,
        passed_threshold=True, reject_reason="",
        false_alarm_probability=1e-5, raw_stats={},
    )


def _score(target: str = "TIC-100", sector: int = 1) -> QualityScore:
    return QualityScore(
        target_id=target, sector=sector, total_score=72.0,
        candidate_class=CandidateClass.B,
        class_description="test",
        components=[
            ScoreComponent(name="snr", raw_value=12.0, score=85.0, weight=0.5, contribution=42.5),
        ],
        is_anomalous=False, anomaly_flags=[],
        fpp=0.15, fpp_method="heuristic_v1", is_false_positive=False,
    )


def _vetting(target: str = "TIC-100", sector: int = 1) -> VettingReport:
    return VettingReport(
        target_id=target, sector=sector,
        tests=[VettingTest(name="t", verdict=VettingVerdict.PASS, value=1.0, threshold=2.0)],
        n_pass=1, n_fail=0, n_warn=0,
        false_positive_probability=0.15, is_false_positive=False,
    )


def _fit_result(target: str = "TIC-100", sector: int = 1, success: bool = True) -> MAPFitResult:
    derived = DerivedParameters(
        planet_radius_rjup=0.9, planet_radius_rearth=10.0,
        semi_major_axis_au=0.05, inclination_deg=88.5,
        equilibrium_temperature_k=800.0,
    )
    return MAPFitResult(
        target_id=target, sector=sector, success=success,
        period=5.0, period_err=0.001, t0=100.0, rp_rs=0.08,
        impact_parameter=0.3, a_over_rs=8.5, inclination=88.5,
        u1=0.3, u2=0.2, log_jitter=-7.0, baseline=1.0,
        log_likelihood=-1234.5, residual_rms=0.0008,
        derived=derived, n_iterations=42,
        optimizer_message="ok", fit_method="map",
    )


def _stellar() -> StellarProperties:
    return StellarProperties(
        tic_id=100, ra=45.0, dec=-20.0, teff=5800.0, logg=4.4,
        radius=1.05, mass=1.0, tmag=10.5, source="TIC",
    )


# ─────────────────────────────────────────────────────────────
# VisualizationReport.to_dict
# ─────────────────────────────────────────────────────────────

def test_report_to_dict_empty() -> None:
    r = VisualizationReport(target_id="TIC-1", sector=1)
    d = r.to_dict()
    assert d["target_id"] == "TIC-1"
    assert d["sector"] == 1
    assert d["figures"]["summary_panel"] is None
    assert d["figures"]["lightcurve"] is None


def test_report_to_dict_with_paths(tmp_path: Path) -> None:
    r = VisualizationReport(
        target_id="TIC-1", sector=1,
        summary_panel=tmp_path / "summary.png",
        lightcurve=tmp_path / "lc.png",
    )
    d = r.to_dict()
    assert d["figures"]["summary_panel"] == str(tmp_path / "summary.png")
    assert d["figures"]["lightcurve"] == str(tmp_path / "lc.png")
    assert d["figures"]["periodogram"] is None


# ─────────────────────────────────────────────────────────────
# Generator init
# ─────────────────────────────────────────────────────────────

def test_generator_init(settings: Settings) -> None:
    gen = VisualizationReportGenerator(settings=settings)
    assert gen.settings is settings
    assert gen._figure_dir.exists()


def test_generator_init_default_settings() -> None:
    """settings=None -> get_settings() kullanilir (hata vermemeli)."""
    gen = VisualizationReportGenerator(settings=None)
    assert gen.settings is not None


# ─────────────────────────────────────────────────────────────
# generate(): save_figures=False
# ─────────────────────────────────────────────────────────────

def test_generate_disabled_returns_empty_report(tmp_path: Path) -> None:
    s = _settings(tmp_path, save_figures=False)
    gen = VisualizationReportGenerator(settings=s)
    report = gen.generate(detrended=_detrended())
    assert report.summary_panel is None
    assert report.lightcurve is None
    assert report.periodogram is None
    assert report.folded is None
    assert report.residuals is None
    assert report.timing is None
    assert report.scorecard is None


# ─────────────────────────────────────────────────────────────
# generate(): minimal
# ─────────────────────────────────────────────────────────────

def test_generate_only_detrended(generator: VisualizationReportGenerator) -> None:
    """Sadece detrended verilir -> sadece lightcurve."""
    report = generator.generate(detrended=_detrended())
    assert report.target_id == "TIC-100"
    assert report.lightcurve is not None
    assert report.lightcurve.exists()
    # digerleri None
    assert report.periodogram is None
    assert report.folded is None
    assert report.timing is None
    assert report.scorecard is None
    assert report.summary_panel is None


def test_generate_with_normalized(generator: VisualizationReportGenerator) -> None:
    """normalized verilirse plot_raw_and_detrended cagrilir."""
    report = generator.generate(
        detrended=_detrended(),
        normalized=_normalized(),
    )
    assert report.lightcurve is not None
    assert report.lightcurve.exists()


# ─────────────────────────────────────────────────────────────
# generate(): periodogram
# ─────────────────────────────────────────────────────────────

def test_generate_with_bls_only(generator: VisualizationReportGenerator) -> None:
    """Sadece BLS -> plot_bls. Periodogram report alani BOS kalir
    (sadece BLS+TLS comparison set ediyor)."""
    report = generator.generate(
        detrended=_detrended(),
        bls_result=_bls_result(),
    )
    # bls-only cagrisi dosya uretir ama report.periodogram set edilmez
    # (kod okuma: sadece BLS+TLS varsa periodogram report alanina yaziyor)
    # Bu davranisi kayit altina aliyoruz.
    assert report.target_id == "TIC-100"


def test_generate_with_bls_and_tls(generator: VisualizationReportGenerator) -> None:
    report = generator.generate(
        detrended=_detrended(),
        bls_result=_bls_result(),
        tls_result=_tls_result(),
    )
    assert report.periodogram is not None
    assert report.periodogram.exists()


# ─────────────────────────────────────────────────────────────
# generate(): folded
# ─────────────────────────────────────────────────────────────

def test_generate_with_candidate(generator: VisualizationReportGenerator) -> None:
    report = generator.generate(
        detrended=_detrended(),
        candidate=_candidate(),
    )
    assert report.folded is not None
    assert report.folded.exists()
    assert report.timing is not None
    assert report.timing.exists()


def test_generate_with_candidate_and_tls(generator: VisualizationReportGenerator) -> None:
    report = generator.generate(
        detrended=_detrended(),
        candidate=_candidate(),
        tls_result=_tls_result(),
    )
    assert report.folded is not None
    assert report.folded.exists()


# ─────────────────────────────────────────────────────────────
# generate(): scorecard
# ─────────────────────────────────────────────────────────────

def test_generate_with_scorecard(generator: VisualizationReportGenerator) -> None:
    report = generator.generate(
        detrended=_detrended(),
        score=_score(),
        vetting=_vetting(),
    )
    assert report.scorecard is not None
    assert report.scorecard.exists()


# ─────────────────────────────────────────────────────────────
# generate(): residual (fit ile)
# ─────────────────────────────────────────────────────────────

def test_generate_with_fit_result(generator: VisualizationReportGenerator) -> None:
    report = generator.generate(
        detrended=_detrended(),
        fit_result=_fit_result(success=True),
    )
    assert report.residuals is not None
    assert report.residuals.exists()


def test_generate_with_failed_fit_no_residual(generator: VisualizationReportGenerator) -> None:
    """success=False -> residual atlanir."""
    report = generator.generate(
        detrended=_detrended(),
        fit_result=_fit_result(success=False),
    )
    assert report.residuals is None


# ─────────────────────────────────────────────────────────────
# generate(): summary panel (tum parametreler)
# ─────────────────────────────────────────────────────────────

def test_generate_full_pipeline(generator: VisualizationReportGenerator) -> None:
    report = generator.generate(
        detrended=_detrended(),
        normalized=_normalized(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        tls_result=_tls_result(),
        score=_score(),
        vetting=_vetting(),
        fit_result=_fit_result(success=True),
        stellar_props=_stellar(),
    )
    # Beklenen: hepsi uretilmis
    assert report.lightcurve is not None
    assert report.periodogram is not None
    assert report.folded is not None
    assert report.residuals is not None
    assert report.timing is not None
    assert report.scorecard is not None
    assert report.summary_panel is not None


def test_generate_summary_panel_requires_core(generator: VisualizationReportGenerator) -> None:
    """Summary panel icin candidate + bls + score + vetting zorunlu."""
    # Eksik: score, vetting -> summary panel uretilmez
    report = generator.generate(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
    )
    assert report.summary_panel is None


# ─────────────────────────────────────────────────────────────
# generate(): robustluk (hatalari yutar)
# ─────────────────────────────────────────────────────────────

def test_generate_handles_exception_in_plotter(generator: VisualizationReportGenerator) -> None:
    """Bozuk bir candidate verildiginde generate() CRASH ETMEMELI.

    Plotter'lar icindeki try/except sayesinde exception yutulur ve
    rapor (kismi veya bos) dondurulur. Burada asil kontrol:
    exception propagate olmuyor.
    """
    # Bozuk candidate -> tum candidate-bagimli plotter'lar basarisiz olur
    # ama generate() yine de VisualizationReport dondurur.
    report = generator.generate(
        detrended=_detrended(),
        candidate="not a candidate",  # type: ignore[arg-type]
    )
    # Asil kontrol: crash yok, rapor nesnesi var
    assert isinstance(report, VisualizationReport)
    assert report.target_id == "TIC-100"
    # candidate-bagimli paneller basarisiz olmus olmali
    assert report.folded is None
    assert report.timing is None
    assert report.summary_panel is None


# ─────────────────────────────────────────────────────────────
# generate(): target_id handling
# ─────────────────────────────────────────────────────────────

def test_generate_safe_id_in_filenames(generator: VisualizationReportGenerator) -> None:
    """target_id icindeki bosluklar dosya adinda _'ya cevrilir."""
    report = generator.generate(
        detrended=_detrended(target="TIC 42"),
    )
    assert report.lightcurve is not None
    assert " " not in report.lightcurve.name
    assert "TIC_42" in report.lightcurve.name


def test_generate_empty_report_when_disabled(tmp_path: Path) -> None:
    """save_figures=False iken VisualizasyonReport null dolu."""
    s = _settings(tmp_path, save_figures=False)
    gen = VisualizationReportGenerator(settings=s)
    report = gen.generate(
        detrended=_detrended(),
        candidate=_candidate(),
        bls_result=_bls_result(),
        score=_score(),
        vetting=_vetting(),
    )
    # Hicbir alan set edilmemis olmali
    d = report.to_dict()
    for k, v in d["figures"].items():
        assert v is None, f"{k} set edildi ama save_figures=False"
