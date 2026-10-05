"""astrotransit/settings.py için kapsamlı testler (validator coverage)."""
from __future__ import annotations

import pytest

from astrotransit.settings import (
    BenchmarkConfig,
    BLSConfig,
    CascadeConfig,
    DetectionConfig,
    DetrendingConfig,
    GeneralConfig,
    JWSTConfig,
    LongPeriodConfig,
    MAPConfig,
    MCMCConfig,
    ModelingConfig,
    OutputsConfig,
    PreprocessingConfig,
    QualityConfig,
    Settings,
    TESSConfig,
    TLSConfig,
)

# ═══════════════════════════════════════════════════════
# GeneralConfig
# ═══════════════════════════════════════════════════════

def test_general_defaults():
    g = GeneralConfig()
    assert g.log_level == "INFO"
    assert g.random_seed == 42


def test_general_log_level_lowercase_upper():
    g = GeneralConfig(log_level="debug")
    assert g.log_level == "DEBUG"


def test_general_invalid_log_level():
    with pytest.raises(ValueError, match="log_level"):
        GeneralConfig(log_level="VERBOSE")


# ═══════════════════════════════════════════════════════
# TESSConfig
# ═══════════════════════════════════════════════════════

def test_tess_defaults():
    t = TESSConfig()
    assert t.author == "SPOC"
    assert t.exptime == 120
    assert t.quality_bitmask == "default"


def test_tess_cache_ttl_invalid():
    with pytest.raises(ValueError, match="cache_ttl_hours"):
        TESSConfig(cache_ttl_hours=0)
    with pytest.raises(ValueError, match="cache_ttl_hours"):
        TESSConfig(cache_ttl_hours=-5)


def test_tess_exptime_invalid():
    with pytest.raises(ValueError, match="exptime"):
        TESSConfig(exptime=30)


def test_tess_quality_bitmask_bool_rejected():
    with pytest.raises(ValueError, match="quality_bitmask"):
        TESSConfig(quality_bitmask=True)


def test_tess_quality_bitmask_negative_int():
    with pytest.raises(ValueError, match="negatif"):
        TESSConfig(quality_bitmask=-1)


def test_tess_quality_bitmask_int_ok():
    t = TESSConfig(quality_bitmask=175)
    assert t.quality_bitmask == 175


def test_tess_quality_bitmask_string_upper():
    t = TESSConfig(quality_bitmask="HARD")
    assert t.quality_bitmask == "hard"


def test_tess_quality_bitmask_unknown_string():
    with pytest.raises(ValueError, match="geçersiz"):
        TESSConfig(quality_bitmask="unknown")


def test_tess_quality_bitmask_empty_string():
    with pytest.raises(ValueError, match="boş"):
        TESSConfig(quality_bitmask="")


def test_tess_quality_bitmask_non_string():
    with pytest.raises(ValueError):
        TESSConfig(quality_bitmask=[1, 2])


# ═══════════════════════════════════════════════════════
# JWSTConfig
# ═══════════════════════════════════════════════════════

def test_jwst_defaults():
    j = JWSTConfig()
    assert j.cache_ttl_hours == 48
    assert j.product_type == "stage3"
    assert "NIRSpec" in j.instruments


def test_jwst_cache_ttl_invalid():
    with pytest.raises(ValueError, match="cache_ttl_hours"):
        JWSTConfig(cache_ttl_hours=0)


def test_jwst_product_type_invalid():
    with pytest.raises(ValueError, match="product_type"):
        JWSTConfig(product_type="stage99")


def test_jwst_product_type_upper():
    j = JWSTConfig(product_type="STAGE2")
    assert j.product_type == "stage2"


# ═══════════════════════════════════════════════════════
# DetrendingConfig
# ═══════════════════════════════════════════════════════

def test_detrending_defaults():
    d = DetrendingConfig()
    assert d.method == "biweight"
    assert d.window_length == 0.5


def test_detrending_window_invalid():
    with pytest.raises(ValueError, match="pozitif"):
        DetrendingConfig(window_length=0)
    with pytest.raises(ValueError, match="pozitif"):
        DetrendingConfig(break_tolerance=-1.0)


def test_detrending_method_invalid():
    with pytest.raises(ValueError, match="method"):
        DetrendingConfig(method="fancy")


def test_detrending_method_upper():
    d = DetrendingConfig(method="COSINE")
    assert d.method == "cosine"


# ═══════════════════════════════════════════════════════
# PreprocessingConfig
# ═══════════════════════════════════════════════════════

def test_preprocessing_defaults():
    p = PreprocessingConfig()
    assert p.sigma_clip_upper == 5.0
    assert p.nan_fill_method == "interpolate"
    assert isinstance(p.detrending, DetrendingConfig)


def test_preprocessing_sigma_clip_invalid():
    with pytest.raises(ValueError, match="pozitif"):
        PreprocessingConfig(sigma_clip_upper=0)
    with pytest.raises(ValueError, match="pozitif"):
        PreprocessingConfig(sigma_clip_lower=-1.0)


def test_preprocessing_nan_fill_invalid():
    with pytest.raises(ValueError, match="nan_fill_method"):
        PreprocessingConfig(nan_fill_method="ffill")


def test_preprocessing_nan_fill_upper():
    p = PreprocessingConfig(nan_fill_method="MEDIAN")
    assert p.nan_fill_method == "median"


# ═══════════════════════════════════════════════════════
# BLSConfig
# ═══════════════════════════════════════════════════════

def test_bls_defaults():
    b = BLSConfig()
    assert b.duration_range == [0.01, 0.2]
    assert b.n_durations == 20


def test_bls_duration_range_wrong_length():
    with pytest.raises(ValueError, match="duration_range"):
        BLSConfig(duration_range=[0.1])


def test_bls_duration_range_inverted():
    with pytest.raises(ValueError, match="duration_range"):
        BLSConfig(duration_range=[0.5, 0.1])


def test_bls_duration_range_zero_first():
    with pytest.raises(ValueError, match="duration_range"):
        BLSConfig(duration_range=[0.0, 0.5])


def test_bls_n_durations_too_small():
    with pytest.raises(ValueError, match="n_durations"):
        BLSConfig(n_durations=1)


# ═══════════════════════════════════════════════════════
# TLSConfig
# ═══════════════════════════════════════════════════════

def test_tls_defaults():
    t = TLSConfig()
    assert t.min_sde_threshold == 6.0
    assert t.oversampling_factor == 3


def test_tls_period_window_too_low():
    with pytest.raises(ValueError, match="period_search_window"):
        TLSConfig(period_search_window=0.0)


def test_tls_period_window_too_high():
    with pytest.raises(ValueError, match="period_search_window"):
        TLSConfig(period_search_window=1.0)


def test_tls_period_window_ok():
    t = TLSConfig(period_search_window=0.5)
    assert t.period_search_window == 0.5


# ═══════════════════════════════════════════════════════
# CascadeConfig
# ═══════════════════════════════════════════════════════

def test_cascade_defaults():
    c = CascadeConfig()
    assert c.require_both is True
    assert c.period_tolerance == 0.01


# ═══════════════════════════════════════════════════════
# LongPeriodConfig
# ═══════════════════════════════════════════════════════

def test_long_period_defaults():
    lp = LongPeriodConfig()
    assert lp.enabled is True
    assert lp.min_period_days == 20.0
    assert lp.max_period_days == 500.0


def test_long_period_min_period_zero():
    with pytest.raises(ValueError, match="pozitif"):
        LongPeriodConfig(min_period_days=0)


def test_long_period_max_period_negative():
    with pytest.raises(ValueError, match="pozitif"):
        LongPeriodConfig(max_period_days=-10.0)


def test_long_period_min_power_zero():
    with pytest.raises(ValueError, match="pozitif"):
        LongPeriodConfig(min_power=0)


def test_long_period_min_depth_zero():
    with pytest.raises(ValueError, match="pozitif"):
        LongPeriodConfig(min_depth=0)


def test_long_period_max_depth_zero():
    with pytest.raises(ValueError, match="pozitif"):
        LongPeriodConfig(max_depth=0)


def test_long_period_counts_too_small():
    with pytest.raises(ValueError, match="en az 1"):
        LongPeriodConfig(n_durations=0)
    with pytest.raises(ValueError, match="en az 1"):
        LongPeriodConfig(n_peaks=0)
    with pytest.raises(ValueError, match="en az 1"):
        LongPeriodConfig(min_points_per_transit=0)


def test_long_period_min_ge_max():
    with pytest.raises(ValueError, match="min_period_days < max_period_days"):
        LongPeriodConfig(min_period_days=100.0, max_period_days=50.0)


def test_long_period_depth_range_invalid():
    with pytest.raises(ValueError, match="min_depth < max_depth"):
        LongPeriodConfig(min_depth=0.5, max_depth=0.1)


# ═══════════════════════════════════════════════════════
# DetectionConfig
# ═══════════════════════════════════════════════════════

def test_detection_defaults():
    d = DetectionConfig()
    assert d.min_period == 0.3
    assert isinstance(d.bls, BLSConfig)
    assert isinstance(d.tls, TLSConfig)
    assert isinstance(d.cascade, CascadeConfig)
    assert isinstance(d.long_period, LongPeriodConfig)


# ═══════════════════════════════════════════════════════
# MAPConfig / MCMCConfig
# ═══════════════════════════════════════════════════════

def test_map_defaults():
    m = MAPConfig()
    assert m.optimizer == "scipy"
    assert m.max_iterations == 2000


def test_mcmc_defaults():
    m = MCMCConfig()
    assert m.sampler == "nuts"
    assert m.chains == 2
    assert m.mcmc_snr_threshold == 10.0


# ═══════════════════════════════════════════════════════
# ModelingConfig
# ═══════════════════════════════════════════════════════

def test_modeling_defaults():
    m = ModelingConfig()
    assert m.fit_method == "map"
    assert m.mcmc_auto_upgrade is True


def test_modeling_fit_method_invalid():
    with pytest.raises(ValueError, match="fit_method"):
        ModelingConfig(fit_method="emcee")


def test_modeling_fit_method_upper():
    m = ModelingConfig(fit_method="MCMC")
    assert m.fit_method == "mcmc"


# ═══════════════════════════════════════════════════════
# QualityConfig
# ═══════════════════════════════════════════════════════

def test_quality_defaults():
    q = QualityConfig()
    assert q.min_snr == 5.0
    assert q.earth_similarity_profile == "photometric_earth_analog"


def test_quality_earth_profile_invalid():
    with pytest.raises(ValueError, match="earth_similarity_profile"):
        QualityConfig(earth_similarity_profile="unknown_profile")


def test_quality_earth_profile_upper():
    q = QualityConfig(earth_similarity_profile="STRICT_EARTH_TWIN")
    assert q.earth_similarity_profile == "strict_earth_twin"


# ═══════════════════════════════════════════════════════
# OutputsConfig
# ═══════════════════════════════════════════════════════

def test_outputs_defaults():
    o = OutputsConfig()
    assert "parquet" in o.formats
    assert o.figure_dpi == 150


# ═══════════════════════════════════════════════════════
# BenchmarkConfig
# ═══════════════════════════════════════════════════════

def test_benchmark_defaults():
    b = BenchmarkConfig()
    assert b.period_tolerance_fraction == 0.02
    assert b.radius_tolerance_fraction == 0.20


def test_benchmark_tolerance_zero():
    with pytest.raises(ValueError, match="tolerans"):
        BenchmarkConfig(period_tolerance_fraction=0.0)


def test_benchmark_tolerance_above_one():
    with pytest.raises(ValueError, match="tolerans"):
        BenchmarkConfig(radius_tolerance_fraction=1.5)


# ═══════════════════════════════════════════════════════
# Settings ana model
# ═══════════════════════════════════════════════════════

def test_settings_default():
    s = Settings()
    assert isinstance(s.general, GeneralConfig)
    assert isinstance(s.tess, TESSConfig)
    assert isinstance(s.jwst, JWSTConfig)
    assert isinstance(s.detection, DetectionConfig)
    assert isinstance(s.modeling, ModelingConfig)
    assert isinstance(s.quality, QualityConfig)
    assert isinstance(s.outputs, OutputsConfig)
    assert isinstance(s.benchmark, BenchmarkConfig)


# ═══════════════════════════════════════════════════════
# get_settings singleton + cache
# ═══════════════════════════════════════════════════════

def test_get_settings_singleton_cache():
    """İlk çağrıda yükler, ikinci çağrıda aynı objeyi döner."""
    import astrotransit.settings as mod
    mod._default_settings = None  # reset

    s1 = mod.get_settings()
    s2 = mod.get_settings()
    assert s1 is s2


def test_get_settings_reload_with_path(tmp_path):
    """Farklı config_path verilirse yeniden yükler."""
    import astrotransit.settings as mod
    mod._default_settings = None

    # Boş TOML oluştur
    config = tmp_path / "custom.toml"
    config.write_text('log_level = "INFO"\n', encoding="utf-8")

    s1 = mod.get_settings()
    # Farklı path ile çağır → reload
    s2 = mod.get_settings(config_path=config)
    assert s2 is not s1

    mod._default_settings = None  # cleanup


def test_load_settings_missing_file_raises(tmp_path):
    """Olmayan dosya → FileNotFoundError."""
    from astrotransit.settings import load_settings
    with pytest.raises(FileNotFoundError, match="bulunamadı"):
        load_settings(tmp_path / "missing.toml")


def test_load_settings_with_project_key(tmp_path):
    """[project] anahtarı Settings'e geçirilmemeli."""
    from astrotransit.settings import load_settings
    config = tmp_path / "with_project.toml"
    config.write_text(
        '[project]\nname = "AstroTransit"\nversion = "1.0"\n\n'
        '[general]\nlog_level = "DEBUG"\n',
        encoding="utf-8",
    )
    s = load_settings(config)
    assert s.general.log_level == "DEBUG"


def test_load_toml_missing():
    from pathlib import Path

    from astrotransit.settings import load_toml
    with pytest.raises(FileNotFoundError):
        load_toml(Path("/nonexistent/path/config.toml"))


def test_load_toml_ok(tmp_path):
    from astrotransit.settings import load_toml
    p = tmp_path / "test.toml"
    p.write_text('[x]\nkey = 1\n', encoding="utf-8")
    data = load_toml(p)
    assert data["x"]["key"] == 1
