"""
JWST light curve detrending modülü.

JWST zaman serisi gözlemleri için Gaussian Process (GP) tabanlı
sistematik gürültü modelleme ve trend giderme.

TESS'ten temel farklılıklar:
    - JWST daha kısa ama çok daha hassas zaman serileri üretir.
    - Enstrüman sistematiği (ramp, drift) GP ile modellenir.
    - celerite2 kütüphanesi kullanılır.
    - Her gözlem tek bir transit penceresi içerir (genellikle).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

try:
    import celerite2
    from celerite2 import terms
    _CELERITE2_AVAILABLE = True
except ImportError:
    _CELERITE2_AVAILABLE = False
    logger.warning("celerite2 kütüphanesi bulunamadı. JWST GP detrending devre dışı.")

try:
    from scipy.optimize import minimize
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


# ──────────────────────────────────────
# JWST light curve veri modeli
# ──────────────────────────────────────
@dataclass
class JWSTObservationData:
    """
    Ham JWST zaman serisi gözlem verisi.

    Attributes
    ----------
    target_id : str
        Hedef adı veya TIC ID.
    program_id : str
        JWST program numarası.
    instrument : str
        Enstrüman adı (NIRSpec, NIRISS, MIRI, NIRCam).
    time : np.ndarray
        Zaman dizisi (MJD veya BJD).
    flux : np.ndarray
        White-light veya kanal bazlı flux dizisi.
    flux_err : np.ndarray
        Flux hata dizisi.
    wavelength_um : Optional[float]
        Referans dalga boyu (mikrometre).
    time_format : str
        Zaman formatı.
    meta : dict
        Ek metadata.
    """

    target_id: str
    program_id: str
    instrument: str
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    wavelength_um: Optional[float] = None
    time_format: str = "bjd"
    meta: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return len(self.time)

    @property
    def duration_hours(self) -> float:
        if len(self.time) < 2:
            return 0.0
        return float((self.time[-1] - self.time[0]) * 24.0)


@dataclass
class JWSTDetrendedData:
    """
    GP ile trend giderilmiş JWST verisi.

    Attributes
    ----------
    target_id : str
        Hedef adı.
    instrument : str
        Enstrüman.
    time : np.ndarray
        Zaman dizisi.
    flux : np.ndarray
        GP trend giderilmiş flux.
    flux_err : np.ndarray
        Hata dizisi.
    gp_mean : np.ndarray
        GP tarafından fit edilen trend bileşeni.
    raw_flux : np.ndarray
        Orijinal flux (referans).
    gp_params : dict
        Optimize edilen GP parametreleri.
    log_likelihood : float
        GP log-likelihood değeri.
    meta : dict
        Ek metadata.
    """

    target_id: str
    instrument: str
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    gp_mean: np.ndarray
    raw_flux: np.ndarray
    gp_params: dict
    log_likelihood: float
    meta: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return len(self.time)

    @property
    def residual_rms(self) -> float:
        residual = self.flux - 1.0
        return float(np.sqrt(np.nanmean(residual ** 2)))

    @property
    def noise_ppm(self) -> float:
        return float(np.nanstd(self.flux - 1.0) * 1e6)

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "instrument": self.instrument,
            "n_points": self.n_points,
            "residual_rms": round(self.residual_rms, 8),
            "noise_ppm": round(self.noise_ppm, 2),
            "log_likelihood": round(self.log_likelihood, 4),
            "gp_params": self.gp_params,
        }


# ──────────────────────────────────────
# GP detrending sınıfı
# ──────────────────────────────────────
class JWSTGPDetrending:
    """
    JWST zaman serisi için Gaussian Process detrending.

    celerite2 kütüphanesi ile SHO (Stochastically-driven
    Harmonic Oscillator) kernel kullanılarak enstrüman
    sistematiği modellenir.

    Transit penceresindeki noktalar GP fit'inden maskelenerek
    transit sinyalinin bozulması önlenir.

    Parameters
    ----------
    sigma_outlier : float
        Ön temizleme sigma kırpma eşiği.
    n_restarts : int
        GP optimizasyon yeniden başlatma sayısı.
    mask_transit : bool
        Transit penceresindeki noktalar maskelensin mi.
    """

    def __init__(
        self,
        sigma_outlier: float = 5.0,
        n_restarts: int = 3,
        mask_transit: bool = True,
    ):
        if not _CELERITE2_AVAILABLE:
            raise ImportError(
                "celerite2 gereklidir: pip install celerite2"
            )
        if not _SCIPY_AVAILABLE:
            raise ImportError(
                "scipy gereklidir: pip install scipy"
            )

        self.sigma_outlier = sigma_outlier
        self.n_restarts = n_restarts
        self.mask_transit = mask_transit

        logger.debug(
            f"JWSTGPDetrending — "
            f"sigma: {sigma_outlier}, "
            f"restarts: {n_restarts}, "
            f"mask_transit: {mask_transit}"
        )

    def _build_gp(
        self,
        time: np.ndarray,
        flux_err: np.ndarray,
        log_sigma: float,
        log_rho: float,
        log_Q: float,
    ) -> celerite2.GaussianProcess:
        """
        SHO kernel ile GP nesnesi oluşturur.

        Parameters
        ----------
        time : np.ndarray
            Zaman dizisi.
        flux_err : np.ndarray
            Hata dizisi.
        log_sigma, log_rho, log_Q : float
            GP kernel log-parametreleri.

        Returns
        -------
        celerite2.GaussianProcess
            GP nesnesi.
        """

        sigma = np.exp(log_sigma)
        rho = np.exp(log_rho)
        Q = np.exp(log_Q)

        kernel = terms.SHOTerm(sigma=sigma, rho=rho, Q=Q)
        gp = celerite2.GaussianProcess(kernel, mean=1.0)
        gp.compute(time, yerr=flux_err)

        return gp

    def _negative_log_likelihood(
        self,
        params: np.ndarray,
        time: np.ndarray,
        flux: np.ndarray,
        flux_err: np.ndarray,
    ) -> float:
        """GP negatif log-likelihood (minimize için)."""

        log_sigma, log_rho, log_Q = params

        try:
            gp = self._build_gp(time, flux_err, log_sigma, log_rho, log_Q)
            return -gp.log_likelihood(flux)
        except Exception:
            return np.inf

    def _optimize_gp(
        self,
        time: np.ndarray,
        flux: np.ndarray,
        flux_err: np.ndarray,
    ) -> tuple[dict, float]:
        """
        GP hiperparametrelerini optimize eder.

        Returns
        -------
        tuple[dict, float]
            Optimize parametreler ve log-likelihood.
        """

        rng = np.random.default_rng(42)

        best_result = None
        best_nll = np.inf

        for _ in range(self.n_restarts):
            # Rastgele başlangıç noktası
            x0 = rng.normal(
                loc=[np.log(np.std(flux)), np.log(1.0), np.log(1.0)],
                scale=[0.5, 0.5, 0.5],
            )

            try:
                result = minimize(
                    self._negative_log_likelihood,
                    x0=x0,
                    args=(time, flux, flux_err),
                    method="L-BFGS-B",
                    options={"maxiter": 1000},
                )

                if result.fun < best_nll:
                    best_nll = result.fun
                    best_result = result

            except Exception as e:
                logger.debug(f"GP optimizasyon denemesi başarısız: {e}")
                continue

        if best_result is None:
            raise RuntimeError("GP hiperparametre optimizasyonu başarısız.")

        params = {
            "log_sigma": float(best_result.x[0]),
            "log_rho": float(best_result.x[1]),
            "log_Q": float(best_result.x[2]),
            "sigma": float(np.exp(best_result.x[0])),
            "rho": float(np.exp(best_result.x[1])),
            "Q": float(np.exp(best_result.x[2])),
        }

        return params, float(-best_nll)

    def detrend(
        self,
        obs: JWSTObservationData,
        transit_mask: Optional[np.ndarray] = None,
    ) -> JWSTDetrendedData:
        """
        JWST gözlem verisine GP detrending uygular.

        Parameters
        ----------
        obs : JWSTObservationData
            Ham JWST gözlem verisi.
        transit_mask : np.ndarray, opsiyonel
            Boolean dizi — True = transit noktası (GP fit'inden hariç).
            Verilmezse tüm noktalara fit yapılır.

        Returns
        -------
        JWSTDetrendedData
            GP trend giderilmiş veri.
        """

        logger.info(
            f"JWST GP detrending — "
            f"{obs.target_id} [{obs.instrument}], "
            f"{obs.n_points} nokta, "
            f"{obs.duration_hours:.2f} saat"
        )

        time = obs.time.copy()
        flux = obs.flux.copy()
        flux_err = obs.flux_err.copy()

        # ── Ön temizleme: sigma kırpma ──
        median = np.nanmedian(flux)
        std = np.nanstd(flux)
        valid_mask = np.abs(flux - median) < self.sigma_outlier * std
        n_removed = (~valid_mask).sum()

        if n_removed > 0:
            logger.debug(f"Ön temizleme: {n_removed} aykırı nokta çıkarıldı")

        time = time[valid_mask]
        flux = flux[valid_mask]
        flux_err = flux_err[valid_mask]

        if transit_mask is not None:
            transit_mask = transit_mask[valid_mask]

        # ── Normalize et ──
        norm_factor = np.nanmedian(flux)
        flux_norm = flux / norm_factor
        flux_err_norm = flux_err / norm_factor

        # ── Transit maskesi uygula (GP fit için) ──
        if transit_mask is not None and self.mask_transit:
            fit_mask = ~transit_mask
            logger.debug(
                f"Transit maskesi uygulandı: "
                f"{fit_mask.sum()} nokta GP fit için kullanılacak"
            )
        else:
            fit_mask = np.ones(len(time), dtype=bool)

        fit_time = time[fit_mask]
        fit_flux = flux_norm[fit_mask]
        fit_err = flux_err_norm[fit_mask]

        if len(fit_time) < 20:
            raise ValueError(
                f"GP fit için yetersiz nokta: {len(fit_time)}"
            )

        # ── GP optimizasyonu ──
        logger.debug("GP hiperparametre optimizasyonu...")
        gp_params, log_like = self._optimize_gp(fit_time, fit_flux, fit_err)

        # ── GP ile tüm zaman noktalarında trend tahmin et ──
        gp = self._build_gp(
            fit_time,
            fit_err,
            gp_params["log_sigma"],
            gp_params["log_rho"],
            gp_params["log_Q"],
        )
        gp.compute(fit_time, yerr=fit_err)

        # Tüm noktalarda GP mean hesapla
        gp_mean = gp.predict(fit_flux, t=time, return_cov=False)

        # ── Trend çıkar ──
        detrended_flux = flux_norm / gp_mean
        detrended_err = flux_err_norm / np.abs(gp_mean)

        # Geçersiz noktaları filtrele
        valid = np.isfinite(detrended_flux) & (gp_mean > 0)
        n_invalid = (~valid).sum()

        if n_invalid > 0:
            logger.debug(f"GP sonrası {n_invalid} geçersiz nokta çıkarıldı.")

        result = JWSTDetrendedData(
            target_id=obs.target_id,
            instrument=obs.instrument,
            time=time[valid],
            flux=detrended_flux[valid],
            flux_err=detrended_err[valid],
            gp_mean=gp_mean[valid],
            raw_flux=flux_norm[valid],
            gp_params=gp_params,
            log_likelihood=log_like,
            meta=obs.meta.copy(),
        )

        logger.info(
            f"JWST GP detrending tamamlandı — "
            f"gürültü: {result.noise_ppm:.1f} ppm, "
            f"log-L: {log_like:.2f}"
        )

        return result