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
from pathlib import Path
from typing import Any, Optional

import numpy as np
from loguru import logger

from astrotransit.settings import Settings, get_settings
from astrotransit.data.mast_client import MASTClient, MASTConnectionError, MASTQueryError
from astrotransit.preprocessing.jwst_detrend import (
    JWSTObservationData,
    JWSTGPDetrending,
    JWSTDetrendedData,
)
from astrotransit.modeling.map_fit import MAPFitter, MAPFitResult
from astrotransit.validation.followup import FollowupEvidence


# ──────────────────────────────────────
# JWST ürün veri sözleşmesi
# ──────────────────────────────────────
@dataclass(frozen=True)
class JWSTProductContract:
    """İşlenebilir bir JWST Stage 2/3 time-series ürünü için sözleşme.

    Metadata araması tek başına bilimsel gözlem değildir. Bu sözleşme, MAST
    kaydından indirilen FITS ürününün gerçekten zaman, flux ve hata sütunlarını
    taşımasını zorunlu kılar; pipeline geçerli olmayan ürünü başarı olarak
    raporlamaz.
    """

    product_path: str | Path
    target_id: str
    obs_id: str
    program_id: str
    instrument: str
    data_level: str = "stage3"
    time_column: str = "TIME"
    flux_column: str = "FLUX"
    flux_err_column: str = "FLUX_ERR"
    time_format: str = "bjd"

    def validate(self) -> None:
        if not str(self.target_id).strip() or not str(self.obs_id).strip():
            raise ValueError("JWST ürününde target_id ve obs_id zorunludur.")
        if not str(self.program_id).strip() or not str(self.instrument).strip():
            raise ValueError("JWST ürününde program_id ve instrument zorunludur.")
        if self.data_level.lower() not in {"stage2", "stage3"}:
            raise ValueError("data_level yalnızca stage2 veya stage3 olabilir.")
        if not str(self.time_column).strip() or not str(self.flux_column).strip():
            raise ValueError("JWST ürününün time ve flux sütunları belirtilmelidir.")


@dataclass(frozen=True)
class JWSTProductValidation:
    """JWST FITS ürününün sözleşme doğrulama sonucu."""

    valid: bool
    product_path: str
    n_points: int = 0
    columns: tuple[str, ...] = ()
    error: str = ""
    time_format: str = "bjd"

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "product_path": self.product_path,
            "n_points": self.n_points,
            "columns": list(self.columns),
            "error": self.error,
            "time_format": self.time_format,
        }


def load_jwst_product(contract: JWSTProductContract) -> tuple[JWSTObservationData | None, JWSTProductValidation]:
    """JWST FITS time-series ürününü doğrular ve ``JWSTObservationData`` üretir."""

    path = Path(contract.product_path)
    try:
        contract.validate()
        if not path.is_file():
            raise FileNotFoundError(f"JWST ürün dosyası bulunamadı: {path}")
        from astropy.io import fits

        with fits.open(path, memmap=False) as hdul:
            required = (contract.time_column, contract.flux_column, contract.flux_err_column)
            selected = None
            table_columns: list[tuple[str, ...]] = []
            for hdu in hdul:
                data = getattr(hdu, "data", None)
                names = getattr(data, "names", None)
                if not names:
                    continue
                columns = tuple(str(name) for name in names)
                table_columns.append(columns)
                upper_to_actual = {name.upper(): name for name in columns}
                if all(name.upper() in upper_to_actual for name in required):
                    selected = (hdu, data, columns, upper_to_actual)
                    break
            if selected is None:
                if not table_columns:
                    raise ValueError("FITS içinde tablo HDU bulunamadı.")
                available = "; ".join(", ".join(columns) for columns in table_columns)
                raise ValueError(
                    "JWST ürününde zorunlu TIME/FLUX/FLUX_ERR sütunları eksik; "
                    f"bulunan sütunlar: {available}"
                )
            hdu, data, columns, upper_to_actual = selected
            time = np.asarray(data[upper_to_actual[contract.time_column.upper()]], dtype=float)
            flux = np.asarray(data[upper_to_actual[contract.flux_column.upper()]], dtype=float)
            flux_err = np.asarray(data[upper_to_actual[contract.flux_err_column.upper()]], dtype=float)
            if time.ndim != 1 or flux.ndim != 1 or flux_err.ndim != 1:
                raise ValueError("JWST time/flux/error sütunları tek boyutlu olmalıdır.")
            if not (len(time) == len(flux) == len(flux_err)) or len(time) < 20:
                raise ValueError("JWST ürününde en az 20 hizalı time/flux/error noktası gerekir.")
            if not (np.all(np.isfinite(time)) and np.all(np.isfinite(flux)) and np.all(np.isfinite(flux_err))):
                raise ValueError("JWST ürününde sonlu olmayan time/flux/error değeri var.")
            if np.any(np.diff(time) <= 0):
                raise ValueError("JWST zaman sütunu kesin artan olmalıdır.")
            if np.any(flux <= 0) or np.any(flux_err <= 0):
                raise ValueError("JWST flux ve flux_err pozitif olmalıdır.")
            header = hdu.header
            meta = {
                "product_path": str(path),
                "data_level": contract.data_level,
                "obs_id": contract.obs_id,
                "program_id": contract.program_id,
                "header_target": str(header.get("TARGNAME", contract.target_id)),
                "header_instrument": str(header.get("INSTRUME", contract.instrument)),
            }
        observation = JWSTObservationData(
            target_id=contract.target_id,
            program_id=contract.program_id,
            instrument=contract.instrument,
            time=time,
            flux=flux,
            flux_err=flux_err,
            time_format=contract.time_format,
            meta=meta,
        )
        validation = JWSTProductValidation(
            valid=True,
            product_path=str(path),
            n_points=len(time),
            columns=columns,
            time_format=contract.time_format,
        )
        return observation, validation
    except Exception as exc:
        return None, JWSTProductValidation(
            valid=False,
            product_path=str(path),
            error=f"{type(exc).__name__}: {exc}",
            time_format=contract.time_format,
        )


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
            "product_validations": [
                result.product_validation
                for result in self.results
                if result.product_validation is not None
            ],
        }

    def to_followup_evidence(
        self,
        *,
        confirmed: bool = False,
        mass_mearth: Optional[float] = None,
        mass_err_mearth: Optional[float] = None,
        false_positive_probability: Optional[float] = None,
    ) -> FollowupEvidence:
        """JWST sonucunu güvenli follow-up kanıtına çevirir.

        Gerçek JWST ürün işleme tamamlanmadan ``confirmed=True`` kabul edilmez;
        mevcut placeholder pipeline yalnızca unconfirmed metadata kanıtı
        üretebilir.
        """

        transit_confirmed = any(
            result.success and result.transit_confirmed
            for result in self.results
        )
        if confirmed and not transit_confirmed:
            raise ValueError(
                "JWST ürününün geçerli olması tek başına transit doğrulaması değildir; "
                "fit sonucu transit_confirmed olmalıdır."
            )
        observation_ids = tuple(
            result.observation_id or result.program_id
            for result in self.results
            if result.observation_id or result.program_id
        )
        if not observation_ids:
            observation_ids = (self.target_id,)
        return FollowupEvidence(
            source="JWST",
            observation_type="jwst_transit",
            observation_ids=observation_ids,
            confirmed=confirmed,
            mass_mearth=mass_mearth,
            mass_err_mearth=mass_err_mearth,
            false_positive_probability=false_positive_probability,
            notes=(
                ()
                if transit_confirmed
                else (
                    "JWST ürünü işlense bile transit fit doğrulaması yok; "
                    "kanıt confirmed değildir.",
                )
            ),
        )


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
    observation_id: str = ""
    product_path: str = ""
    product_validation: Optional[dict[str, Any]] = None
    detrended: Optional[JWSTDetrendedData] = None
    fit_result: Optional[MAPFitResult] = None
    noise_ppm: float = 0.0
    transit_confirmed: bool = False
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

    def process_product(
        self,
        contract: JWSTProductContract,
        *,
        transit_mask: Optional[np.ndarray] = None,
    ) -> JWSTObservationResult:
        """Doğrulanmış bir Stage 2/3 ürünü GP detrending'e bağlar.

        Bu metod metadata araması yerine fiziksel FITS ürününü girdi alır.
        Detrending başarılı olsa bile transit fit'i yapılmadığı için
        ``transit_confirmed`` false kalır; bu sınır follow-up kanıtına yanlış
        onay sızmasını engeller.
        """

        observation, validation = load_jwst_product(contract)
        result = JWSTObservationResult(
            program_id=contract.program_id,
            instrument=contract.instrument,
            observation_id=contract.obs_id,
            product_path=str(contract.product_path),
            product_validation=validation.to_dict(),
        )
        if observation is None:
            result.error = validation.error
            return result
        try:
            detrended = self._gp_detrend.detrend(observation, transit_mask=transit_mask)
        except Exception as exc:
            result.error = f"JWST detrending başarısız: {exc}"
            return result
        result.detrended = detrended
        result.noise_ppm = detrended.noise_ppm
        result.success = True
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
            observation_id=obs_id,
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