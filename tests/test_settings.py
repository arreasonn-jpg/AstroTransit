"""Konfigürasyon sistemi testleri."""

import pytest
from pathlib import Path

from astrotransit.settings import (
    Settings,
    GeneralConfig,
    TESSConfig,
    DetectionConfig,
    QualityConfig,
    load_settings,
)


class TestSettings:
    """Settings nesnesi testleri."""

    def test_default_creation(self):
        s = Settings()
        assert s.general.log_level == "INFO"
        assert s.tess.exptime == 120
        assert s.detection.min_period == 0.3
        assert s.detection.max_period == 30.0

    def test_general_log_level_validation(self):
        with pytest.raises(ValueError):
            GeneralConfig(log_level="INVALID")

    def test_tess_exptime_validation(self):
        with pytest.raises(ValueError):
            TESSConfig(exptime=999)

    def test_tess_valid_exptimes(self):
        for exp in [20, 120, 600]:
            cfg = TESSConfig(exptime=exp)
            assert cfg.exptime == exp

    def test_quality_bitmask_rejects_bool(self):
        with pytest.raises(ValueError):
            TESSConfig(quality_bitmask=True)

    def test_detection_defaults(self):
        d = DetectionConfig()
        assert d.min_period == 0.3
        assert d.max_period == 30.0
        assert d.min_transits == 2
        assert d.bls.min_power_threshold == 7.0
        assert d.tls.min_sde_threshold == 6.0

    def test_earth_similarity_profile_validation(self):
        assert QualityConfig(earth_similarity_profile="STRICT_EARTH_TWIN").earth_similarity_profile == "strict_earth_twin"
        with pytest.raises(ValueError):
            QualityConfig(earth_similarity_profile="unknown_profile")

    def test_load_from_toml(self):
        config_path = Path("configs/default.toml")
        if config_path.exists():
            s = load_settings(config_path)
            assert isinstance(s, Settings)
            assert s.general.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def test_missing_config_file(self):
        with pytest.raises(FileNotFoundError):
            load_settings("/nonexistent/path/config.toml")