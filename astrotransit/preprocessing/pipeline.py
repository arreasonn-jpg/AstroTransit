"""
Ön işleme pipeline orkestratörü.

Normalize → Temizle → Detrend adımlarını tek
bir çağrıda birleştirir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from loguru import logger

from astrotransit.data.tess_client import TESSLightCurveData, TESSMultiSectorData
from astrotransit.preprocessing.normalization import (
    LightCurveNormalizer,
    NormalizationMethod,
    NormalizedLightCurve,
)
from astrotransit.preprocessing.cleaning import LightCurveCleaner, CleanedLightCurve
from astrotransit.preprocessing.tess_detrend import (
    TESSDetrending,
    DetrendMethod,
    DetrendedLightCurve,
)
from astrotransit.settings import Settings, get_settings


@dataclass
class PreprocessedLightCurve:
    """
    Tam ön işleme sürecinden geçmiş light curve.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    normalized : NormalizedLightCurve
        Normalize edilmiş veri.
    cleaned : CleanedLightCurve
        Temizlenmiş veri.
    detrended : DetrendedLightCurve
        Trend giderilmiş veri.
    """

    target_id: str
    sector: int
    normalized: NormalizedLightCurve
    cleaned: CleanedLightCurve
    detrended: DetrendedLightCurve

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "normalization": self.normalized.summary(),
            "cleaning": self.cleaned.summary(),
            "detrending": self.detrended.summary(),
        }


@dataclass
class PreprocessedMultiSector:
    """
    Çok sektörlü ön işleme sonuçları.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sectors : list[PreprocessedLightCurve]
        Sektör bazlı işlenmiş veriler.
    """

    target_id: str
    sectors: list[PreprocessedLightCurve]

    @property
    def n_sectors(self) -> int:
        return len(self.sectors)

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "n_sectors": self.n_sectors,
            "sectors": [s.summary() for s in self.sectors],
        }


class TESSPreprocessingPipeline:
    """
    TESS ön işleme pipeline'ı.

    Normalize → Temizle → Detrend adımlarını
    tek çağrıda birleştirir.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu. Verilmezse varsayılan yüklenir.
    norm_method : str
        Normalizasyon yöntemi.
    detrend_method : str
        Detrending yöntemi.
    window_length : float
        Detrending pencere genişliği (gün).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        norm_method: str = "median",
        detrend_method: str = "biweight",
        window_length: Optional[float] = None,
    ):
        if settings is None:
            settings = get_settings()

        self.settings = settings
        cfg_pre = settings.preprocessing

        # window_length önceliği: parametre > config
        _window = window_length or cfg_pre.detrending.window_length

        # Alt modüller
        self._normalizer = LightCurveNormalizer(method=norm_method)

        self._cleaner = LightCurveCleaner(
            gap_threshold_days=cfg_pre.detrending.break_tolerance,
            sigma_clip_flux=cfg_pre.sigma_clip_upper,
        )

        self._detrend = TESSDetrending(
            method=detrend_method,
            window_length=_window,
            break_tolerance=cfg_pre.detrending.break_tolerance,
        )

        logger.info(
            f"TESSPreprocessingPipeline — "
            f"norm: {norm_method}, "
            f"detrend: {detrend_method}, "
            f"pencere: {_window}d"
        )

    def run(self, data: TESSLightCurveData) -> PreprocessedLightCurve:
        """
        Tek sektör için ön işleme pipeline'ını çalıştırır.

        Parameters
        ----------
        data : TESSLightCurveData
            Ham TESS light curve verisi.

        Returns
        -------
        PreprocessedLightCurve
            Tam işlenmiş light curve.
        """

        logger.info(
            f"Ön işleme pipeline başlıyor — "
            f"{data.target_id} sektör {data.sector}"
        )

        # ── Adım 1: Normalize ──
        normalized = self._normalizer.normalize(data)

        # ── Adım 2: Temizle ──
        cleaned = self._cleaner.clean(normalized)

        # ── Adım 3: Detrend ──
        detrended = self._detrend.detrend(cleaned)

        result = PreprocessedLightCurve(
            target_id=data.target_id,
            sector=data.sector,
            normalized=normalized,
            cleaned=cleaned,
            detrended=detrended,
        )

        logger.info(
            f"Ön işleme tamamlandı — "
            f"{data.target_id} sektör {data.sector}: "
            f"{detrended.n_points} nokta, "
            f"gürültü {detrended.noise_ppm:.1f} ppm"
        )

        return result

    def run_multi(self, multi: TESSMultiSectorData) -> PreprocessedMultiSector:
        """
        Çok sektörlü veri için ön işleme pipeline'ını çalıştırır.

        Parameters
        ----------
        multi : TESSMultiSectorData
            Çok sektörlü ham veri.

        Returns
        -------
        PreprocessedMultiSector
            Tüm sektörler için işlenmiş veriler.
        """

        logger.info(
            f"Çok sektör ön işleme — "
            f"{multi.target_id}: {multi.n_sectors} sektör"
        )

        processed_sectors = []

        for sector_data in multi.sectors:
            try:
                result = self.run(sector_data)
                processed_sectors.append(result)
            except Exception as e:
                logger.warning(
                    f"Sektör {sector_data.sector} ön işleme başarısız: {e}"
                )
                continue

        if not processed_sectors:
            raise RuntimeError(
                f"{multi.target_id}: hiçbir sektör işlenemedi."
            )

        logger.info(
            f"Çok sektör ön işleme tamamlandı — "
            f"{len(processed_sectors)}/{multi.n_sectors} sektör başarılı"
        )

        return PreprocessedMultiSector(
            target_id=multi.target_id,
            sectors=processed_sectors,
        )