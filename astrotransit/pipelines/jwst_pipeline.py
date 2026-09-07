"""
JWST follow-up transit analiz pipeline'ı.

TESS'te tespit edilen adaylar için JWST
verilerinde ileri transit analizi yapar.

İş akışı:
    TESS adayı → JWST veri arama
        ↓
    Stage 2/3 ürün indirme
        ↓
    White-light curve oluşturma
        ↓
    GP detrending (celerite2)
        ↓
    Transit modelleme
        ↓
    Parametre rafinasyonu
        ↓
    Sonuçların kaydı
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.settings import Settings, get_settings
from astrotransit.data.mast_client import MASTClient, MASTConnectionError, MASTQueryError
from astrotransit.preprocessing.jwst_detrend import (
    JWSTObservationData,
    JWSTGPDetrending,
    JWSTDetrendedData,
)
from astrotransit.modeling.parameters import TransitPriors
from astrotransit.modeling.map_fit import MAPFitter, MAPFitResult


# ──────────────────────────────────────
# JWST pipeline sonuç modeli
# ──────────────────────────────────────
@dataclass
class JWSTFollowUpResult:
    """
    JWST follow-up pipeline sonucu.

    Attributes
    ----------
    target_id : str
        Hedef ID.
    tess_period : float
        TESS'ten gelen periyot (gün).
    jwst_programs_found : int
        Bulunan JWST program sayısı.
    observations_processed : int
        İşlenen gözlem sayısı.
    results : list[JWSTObservationResult]
        Gözlem bazlı sonuçlar.
    success : bool
        Pipeline başarılı mı?
    error : str
        Hata mesajı.
    """

    target_id: str
    tess_period: float = 0.0
    jwst_programs_found: int = 0
    observations_processed: int = 0
    results: list = field(default_factory=list)
    success: bool = False
    error: str = ""

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "tess_period": round(self.tess_period, 6),
            "jwst_programs_found": self.jwst_programs_found,
            "observations_processed": self.observations_processed,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class JWSTObservationResult:
    """
    Tek bir JWST gözleminin analiz sonucu.

    Attributes
    ----------
    program_id : str
        JWST program numarası.
    instrument : str
        Enstrüman adı.
    detrended : Optional[JWSTDetrendedData]
        GP detrend sonucu.
    fit_result : Optional[MAPFitResult]
        Transit fit sonucu.
    noise_ppm : float
        Detrend sonrası gürültü (ppm).
    success : bool
        Gözlem başarılı mı?
    error : str
        Hata mesajı.
    """

    program_id: str = ""
    instrument: str = ""
    detrended: Optional[JWSTDetrendedData] = None
    fit_result: Optional[MAPFitResult] = None
    noise_ppm: float = 0.0
    success: bool = False
    error: str = ""


# ──────────────────────────────────────
# JWST Follow-Up Pipeline
# ──────────────────────────────────────
class JWSTFollowUpPipeline:
    """
    JWST follow-up transit analiz pipeline'ı.

    TESS adayları için JWST verisinde transit arar
    ve parametreleri rafine eder.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu.
    """

    def __init__(self, settings: Optional[Settings] = None):
        if settings is None:
            settings = get_settings()

        self.settings = settings

        self._mast = MASTClient()
        self._gp_detrend = JWSTGPDetrending(
            sigma_outlier=5.0,
            n_restarts=3,
            mask_transit=True,
        )
        self._map_fitter = MAPFitter(max_iterations=2000, n_restarts=3)

        logger.info("JWSTFollowUpPipeline başlatıldı.")

    def search_jwst_observations(
        self,
        target_id: str,
    ) -> list[dict]:
        """
        Hedef için JWST time-series gözlemlerini arar.

        Parameters
        ----------
        target_id : str
            Hedef adı veya TIC ID.

        Returns
        -------
        list[dict]
            Bulunan gözlem bilgileri.
        """

        logger.info(f"JWST gözlem araması — {target_id}")

        try:
            results = self._mast.query_observations(
                target_name=target_id,
                obs_collection="JWST",
                dataproduct_type="timeseries",
            )

            observations = []

            for row in results:
                obs_info = {
                    "obs_id": str(row.get("obs_id", "")),
                    "target_name": str(row.get("target_name", "")),
                    "instrument": str(row.get("instrument_name", "")),
                    "filters": str(row.get("filters", "")),
                    "t_min": float(row.get("t_min", 0)),
                    "t_max": float(row.get("t_max", 0)),
                    "proposal_id": str(row.get("proposal_id", "")),
                }
                observations.append(obs_info)

            logger.info(
                f"JWST araması tamamlandı — "
                f"{target_id}: {len(observations)} gözlem"
            )

            return observations

        except (MASTConnectionError, MASTQueryError) as e:
            logger.warning(f"JWST araması başarısız: {e}")
            return []

    def run(
        self,
        target_id: str,
        tess_period: float,
        tess_t0: float,
        tess_duration: float,
        tess_rp_rs: float,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
        stellar_teff: float = 5778.0,
    ) -> JWSTFollowUpResult:
        """
        JWST follow-up pipeline'ını çalıştırır.

        Parameters
        ----------
        target_id : str
            Hedef ID.
        tess_period : float
            TESS'ten gelen periyot (gün).
        tess_t0 : float
            TESS transit merkez zamanı.
        tess_duration : float
            TESS transit süresi (gün).
        tess_rp_rs : float
            TESS Rp/Rs tahmini.
        stellar_radius, stellar_mass, stellar_teff : float
            Yıldız parametreleri.

        Returns
        -------
        JWSTFollowUpResult
            Follow-up sonucu.
        """

        logger.info(
            f"JWST follow-up — {target_id}: "
            f"P={tess_period:.4f}d"
        )

        result = JWSTFollowUpResult(
            target_id=target_id,
            tess_period=tess_period,
        )

        # ── JWST gözlemleri ara ──
        observations = self.search_jwst_observations(target_id)
        result.jwst_programs_found = len(observations)

        if not observations:
            result.error = "JWST gözlemi bulunamadı."
            logger.info(f"{target_id}: JWST verisi yok.")
            return result

        logger.info(
            f"{target_id}: {len(observations)} JWST gözlemi bulundu"
        )

        # ── Her gözlemi işle ──
        for obs_info in observations:
            try:
                obs_result = self._process_observation(
                    obs_info=obs_info,
                    target_id=target_id,
                    tess_period=tess_period,
                    tess_t0=tess_t0,
                    tess_duration=tess_duration,
                    tess_rp_rs=tess_rp_rs,
                    stellar_radius=stellar_radius,
                    stellar_mass=stellar_mass,
                    stellar_teff=stellar_teff,
                )

                result.results.append(obs_result)

                if obs_result.success:
                    result.observations_processed += 1

            except Exception as e:
                logger.error(
                    f"JWST gözlem hatası ({obs_info.get('obs_id', '?')}): {e}"
                )

        result.success = result.observations_processed > 0

        logger.info(
            f"JWST follow-up tamamlandı — "
            f"{target_id}: {result.observations_processed} gözlem işlendi"
        )

        return result

    def _process_observation(
        self,
        obs_info: dict,
        target_id: str,
        tess_period: float,
        tess_t0: float,
        tess_duration: float,
        tess_rp_rs: float,
        stellar_radius: float,
        stellar_mass: float,
        stellar_teff: float,
    ) -> JWSTObservationResult:
        """
        Tek bir JWST gözlemini işler.

        Not: Bu metod şu an iskelet halindedir.
        Gerçek JWST veri indirme ve Stage 2/3 okuma
        sonraki fazda implementasyon gerektirir.
        """

        obs_id = obs_info.get("obs_id", "unknown")
        instrument = obs_info.get("instrument", "unknown")

        logger.info(
            f"JWST gözlem işleniyor — "
            f"{obs_id} [{instrument}]"
        )

        obs_result = JWSTObservationResult(
            program_id=obs_info.get("proposal_id", ""),
            instrument=instrument,
        )

        # ────────────────────────────────
        # PLACEHOLDER: Gerçek JWST veri işleme
        #
        # Bu bölüm sonraki fazlarda implementasyon gerektirir:
        # 1. MAST'tan Stage 2/3 ürün indirme
        # 2. FITS dosyalarından time-series çıkarma
        # 3. White-light curve oluşturma
        # 4. GP detrending (self._gp_detrend.detrend())
        # 5. Transit modelleme (self._map_fitter.fit())
        #
        # Şu an sadece gözlem bilgilerini kaydediyoruz.
        # ────────────────────────────────

        logger.debug(
            f"JWST gözlem {obs_id}: veri işleme placeholder. "
            f"Gerçek implementasyon sonraki fazda."
        )

        # Metadata araması, bilimsel veri ürününün işlendiği anlamına gelmez.
        # Gerçek FITS/GP/MAP adımları hazır olana kadar sonucu açıkça
        # başarısız bırakıyoruz; aksi halde downstream raporları yanıltıcı
        # biçimde başarılı görünecektir.
        obs_result.success = False
        obs_result.error = "JWST veri ürünü işleme henüz implemente edilmedi"

        return obs_result