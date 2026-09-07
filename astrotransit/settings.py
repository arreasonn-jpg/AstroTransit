"""
Merkezi konfigürasyon yönetimi.

default.toml dosyasını okur, doğrular ve tüm modüllere
tek bir Settings nesnesi olarak sunar.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ──────────────────────────────────────
# Python 3.11+ tomllib, altı için tomli
# ──────────────────────────────────────
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        raise ImportError("Python <3.11 için 'tomli' paketi gereklidir: pip install tomli")


# ──────────────────────────────────────
# Alt konfigürasyon modelleri
# ──────────────────────────────────────
class GeneralConfig(BaseModel):
    """Genel proje ayarları."""

    log_level: str = "INFO"
    temp_dir: str = ".cache/astrotransit"
    output_dir: str = "outputs"
    random_seed: int = 42

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level '{v}' geçersiz. İzin verilenler: {allowed}")
        return upper


class TESSConfig(BaseModel):
    """TESS veri erişim ayarları."""

    use_cache: bool = True
    cache_ttl_hours: int = 24
    author: str = "SPOC"
    exptime: int = 120
    quality_bitmask: str = "default"

    @field_validator("exptime")
    @classmethod
    def validate_exptime(cls, v: int) -> int:
        allowed = {20, 120, 600}
        if v not in allowed:
            raise ValueError(f"exptime {v} geçersiz. İzin verilenler: {allowed}")
        return v


class JWSTConfig(BaseModel):
    """JWST veri erişim ayarları."""

    use_cache: bool = True
    cache_ttl_hours: int = 48
    product_type: str = "stage3"
    instruments: list[str] = Field(
        default=["NIRSpec", "NIRISS", "MIRI", "NIRCam"]
    )

    @field_validator("product_type")
    @classmethod
    def validate_product_type(cls, v: str) -> str:
        allowed = {"stage2", "stage3"}
        if v.lower() not in allowed:
            raise ValueError(f"product_type '{v}' geçersiz. İzin verilenler: {allowed}")
        return v.lower()


class DetrendingConfig(BaseModel):
    """Detrending alt ayarları."""

    method: str = "biweight"
    window_length: float = 0.5
    break_tolerance: float = 0.5

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        allowed = {"biweight", "cosine", "gp", "spline"}
        if v.lower() not in allowed:
            raise ValueError(f"detrending method '{v}' geçersiz. İzin verilenler: {allowed}")
        return v.lower()


class PreprocessingConfig(BaseModel):
    """Ön işleme ayarları."""

    sigma_clip_upper: float = 5.0
    sigma_clip_lower: float = 5.0
    nan_fill_method: str = "interpolate"
    detrending: DetrendingConfig = Field(default_factory=DetrendingConfig)

    @field_validator("nan_fill_method")
    @classmethod
    def validate_nan_fill(cls, v: str) -> str:
        allowed = {"interpolate", "median", "drop"}
        if v.lower() not in allowed:
            raise ValueError(f"nan_fill_method '{v}' geçersiz. İzin verilenler: {allowed}")
        return v.lower()


class BLSConfig(BaseModel):
    """BLS arama alt ayarları."""

    duration_range: list[float] = Field(default=[0.01, 0.2])
    n_durations: int = 20
    min_power_threshold: float = 7.0


class TLSConfig(BaseModel):
    """TLS arama alt ayarları."""

    min_sde_threshold: float = 6.0
    use_transit_template: bool = True
    oversampling_factor: int = 3


class CascadeConfig(BaseModel):
    """Kademeli arama alt ayarları."""

    require_both: bool = True
    period_tolerance: float = 0.01


class DetectionConfig(BaseModel):
    """Transit arama ayarları."""

    min_period: float = 0.3
    max_period: float = 30.0
    min_transits: int = 2
    frequency_factor: float = 2.0
    bls: BLSConfig = Field(default_factory=BLSConfig)
    tls: TLSConfig = Field(default_factory=TLSConfig)
    cascade: CascadeConfig = Field(default_factory=CascadeConfig)


class MAPConfig(BaseModel):
    """MAP fit alt ayarları."""

    optimizer: str = "scipy"
    max_iterations: int = 2000


class MCMCConfig(BaseModel):
    """MCMC alt ayarları."""

    sampler: str = "nuts"
    chains: int = 2
    draws: int = 1500
    tune: int = 1000
    target_accept: float = 0.9
    mcmc_snr_threshold: float = 10.0


class ModelingConfig(BaseModel):
    """Modelleme ayarları."""

    fit_method: str = "map"
    mcmc_auto_upgrade: bool = True
    map: MAPConfig = Field(default_factory=MAPConfig)
    mcmc: MCMCConfig = Field(default_factory=MCMCConfig)

    @field_validator("fit_method")
    @classmethod
    def validate_fit_method(cls, v: str) -> str:
        allowed = {"map", "mcmc"}
        if v.lower() not in allowed:
            raise ValueError(f"fit_method '{v}' geçersiz. İzin verilenler: {allowed}")
        return v.lower()


class QualityConfig(BaseModel):
    """Kalite değerlendirme ayarları."""

    min_snr: float = 5.0
    max_residual_rms: float = 0.005
    min_data_completeness: float = 0.80


class OutputsConfig(BaseModel):
    """Çıktı ayarları."""

    formats: list[str] = Field(default=["parquet", "json"])
    extra_formats: list[str] = Field(default=["csv"])
    save_figures: bool = True
    figure_format: str = "png"
    figure_dpi: int = 150
    generate_html_report: bool = False


class BenchmarkConfig(BaseModel):
    """Benchmark ayarları."""

    confirmed_targets_file: str = "benchmarks/tess/confirmed_targets.parquet"
    false_positives_file: str = "benchmarks/tess/false_positives.parquet"
    quiet_stars_file: str = "benchmarks/tess/quiet_stars.parquet"


# ──────────────────────────────────────
# Ana konfigürasyon modeli
# ──────────────────────────────────────
class Settings(BaseModel):
    """
    AstroTransit merkezi konfigürasyon nesnesi.

    Tüm modüller bu nesneye erişerek parametrelerini alır.
    """

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    tess: TESSConfig = Field(default_factory=TESSConfig)
    jwst: JWSTConfig = Field(default_factory=JWSTConfig)
    preprocessing: PreprocessingConfig = Field(default_factory=PreprocessingConfig)
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    modeling: ModelingConfig = Field(default_factory=ModelingConfig)
    quality: QualityConfig = Field(default_factory=QualityConfig)
    outputs: OutputsConfig = Field(default_factory=OutputsConfig)
    benchmark: BenchmarkConfig = Field(default_factory=BenchmarkConfig)


# ──────────────────────────────────────
# Konfigürasyon yükleme fonksiyonları
# ──────────────────────────────────────
def load_toml(path: Path) -> dict:
    """TOML dosyasını okur ve dict olarak döndürür."""

    if not path.exists():
        raise FileNotFoundError(f"Konfigürasyon dosyası bulunamadı: {path}")

    with open(path, "rb") as f:
        return tomllib.load(f)


def load_settings(config_path: Optional[str | Path] = None) -> Settings:
    """
    Konfigürasyon dosyasını yükler ve doğrulanmış Settings nesnesi döndürür.

    Parameters
    ----------
    config_path : str veya Path, opsiyonel
        TOML dosyasının yolu.
        Verilmezse configs/default.toml kullanılır.

    Returns
    -------
    Settings
        Doğrulanmış konfigürasyon nesnesi.
    """

    if config_path is None:
        # Proje kök dizininden default.toml'u bul
        project_root = Path(__file__).resolve().parent.parent
        config_path = project_root / "configs" / "default.toml"
    else:
        config_path = Path(config_path)

    raw = load_toml(config_path)

    # [project] anahtarını ayır (Settings modeline dahil değil)
    raw.pop("project", None)

    return Settings(**raw)


# ──────────────────────────────────────
# Modül seviyesinde varsayılan erişim
# ──────────────────────────────────────
_default_settings: Optional[Settings] = None


def get_settings(config_path: Optional[str | Path] = None) -> Settings:
    """
    Singleton benzeri erişim.

    İlk çağrıda yükler, sonraki çağrılarda önbellek döndürür.
    Farklı bir config_path verilirse yeniden yükler.
    """

    global _default_settings

    if _default_settings is None or config_path is not None:
        _default_settings = load_settings(config_path)

    return _default_settings