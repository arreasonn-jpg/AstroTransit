"""
Modelleme orkestratörü.

MAP ve MCMC fit'lerini yönetir.
SNR eşiğine göre hangi yöntemin
uygulanacağına otomatik karar verir.

Karar akışı:
    CascadeCandidate (confirmed=True)
        ↓
    MAP Fit (her aday için)
        ↓
    SNR < eşik → MAP sonucu nihai
    SNR ≥ eşik → PyMC MCMC (kurulu ise)
"""

from __future__ import annotations

from typing import Optional, Union

from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.modeling.parameters import TransitPriors
from astrotransit.modeling.map_fit import MAPFitter, MAPFitResult
from astrotransit.settings import Settings, get_settings

# PyMC opsiyonel — kurulu değilse sadece MAP kullanılır
try:
    from astrotransit.modeling.pymc_fit import PyMCFitter, MCMCFitResult
    _PYMC_AVAILABLE = True
except ImportError:
    _PYMC_AVAILABLE = False
    PyMCFitter = None
    MCMCFitResult = None

# Birleşik sonuç tipi
if _PYMC_AVAILABLE:
    FitResult = Union[MAPFitResult, MCMCFitResult]
else:
    FitResult = MAPFitResult


class ModelingOrchestrator:
    """
    Transit modelleme orkestratörü.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu.
    stellar_radius : float
        Yıldız yarıçapı (R_sun).
    stellar_mass : float
        Yıldız kütlesi (M_sun).
    stellar_teff : float
        Yıldız efektif sıcaklığı (K).
    force_mcmc : bool
        SNR eşiğinden bağımsız olarak her zaman MCMC çalıştır.
    force_map : bool
        Her zaman sadece MAP kullan (MCMC çalıştırma).
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
        stellar_teff: float = 5778.0,
        force_mcmc: bool = False,
        force_map: bool = False,
    ):
        if settings is None:
            settings = get_settings()

        self.settings = settings
        self.stellar_radius = stellar_radius
        self.stellar_mass = stellar_mass
        self.stellar_teff = stellar_teff
        self.force_mcmc = force_mcmc
        self.force_map = force_map

        mod_cfg = settings.modeling

        self._map_fitter = MAPFitter(
            max_iterations=mod_cfg.map.max_iterations,
            n_restarts=3,
        )

        # PyMC fitter yalnızca kurulu ise ve force_map=False ise
        self._mcmc_fitter = None
        if _PYMC_AVAILABLE and not force_map:
            try:
                self._mcmc_fitter = PyMCFitter(
                    chains=mod_cfg.mcmc.chains,
                    draws=mod_cfg.mcmc.draws,
                    tune=mod_cfg.mcmc.tune,
                    target_accept=mod_cfg.mcmc.target_accept,
                    random_seed=settings.general.random_seed,
                )
            except Exception as e:
                logger.warning(f"PyMCFitter oluşturulamadı: {e}")
                self._mcmc_fitter = None

        self._mcmc_snr_threshold = mod_cfg.mcmc.mcmc_snr_threshold
        self._mcmc_auto_upgrade = mod_cfg.mcmc_auto_upgrade

        mcmc_status = (
            "kurulu değil" if not _PYMC_AVAILABLE
            else "devre dışı" if force_map
            else f"eşik: SNR≥{self._mcmc_snr_threshold}"
        )

        logger.info(
            f"ModelingOrchestrator — "
            f"MCMC: {mcmc_status}, "
            f"force_mcmc: {force_mcmc}, "
            f"force_map: {force_map}"
        )


    def _posterior_center(self, fit_result, name: str):
        """Posterior özetinden merkez değer döndürür."""
        posteriors = getattr(fit_result, "posteriors", None) or {}
        post = posteriors.get(name)
        if post is None:
            return None
        for attr in ("median", "value", "mean"):
            if hasattr(post, attr):
                try:
                    return float(getattr(post, attr))
                except Exception:
                    pass
        if isinstance(post, dict):
            for key in ("median", "value", "mean"):
                if key in post:
                    try:
                        return float(post[key])
                    except Exception:
                        pass
        return None

    def _harmonize_mcmc_result(self, mcmc_result, map_result):
        """
        Başarılı MCMC sonucunu downstream MAP-odaklı output/visualization
        contract'ına uyumlu hale getirir.

        MCMCFitResult bazı alanlara sahip olmayabilir.
        Bu metod eksik alanları map_result'tan tamamlar,
        sonra posterior merkezlerini varsa üstüne yazar.
        """
        attrs_from_map = [
            "period",
            "period_err",
            "t0",
            "duration_hours",
            "depth",
            "depth_ppm",
            "rp_rs",
            "rp_rs_err",
            "impact_parameter",
            "a_over_rs",
            "inclination_deg",
            "u1",
            "u2",
            "baseline",
            "log_jitter",
            "log_likelihood",
            "semi_major_axis_au",
            "stellar_density_gcm3",
            "planet_radius_rearth",
            "planet_radius_rjup",
            "equilibrium_temperature_k",
            "insolation_flux",
            "transit_depth_ppm",
            "residuals",
        ]

        for attr in attrs_from_map:
            if getattr(mcmc_result, attr, None) is None:
                val = getattr(map_result, attr, None)
                if val is not None:
                    try:
                        setattr(mcmc_result, attr, val)
                    except Exception:
                        pass

        # Posterior merkezlerini üstüne yaz (daha iyi MCMC değerleri)
        posterior_map = {
            "baseline": "baseline",
            "log_jitter": "log_jitter",
            "impact_parameter": "impact_parameter",
            "rp_rs": "rp_rs",
            "t0": "t0",
        }
        for attr, post_name in posterior_map.items():
            val = self._posterior_center(mcmc_result, post_name)
            if val is not None:
                try:
                    setattr(mcmc_result, attr, val)
                except Exception:
                    pass

        # Derived bundle varsa oradan da doldur
        derived = getattr(mcmc_result, "derived", None)
        if derived is not None:
            for attr in [
                "planet_radius_rearth",
                "planet_radius_rjup",
                "semi_major_axis_au",
                "equilibrium_temperature_k",
                "insolation_flux",
            ]:
                if getattr(mcmc_result, attr, None) is None:
                    val = getattr(derived, attr, None)
                    if val is not None:
                        try:
                            setattr(mcmc_result, attr, val)
                        except Exception:
                            pass

        # Output contract etiketleri
        for attr, val in [
            ("period_sampled", False),
            ("period_err_source", "fixed_in_mcmc"),
        ]:
            if not hasattr(mcmc_result, attr):
                try:
                    setattr(mcmc_result, attr, val)
                except Exception:
                    pass

        # period_err None olarak bırak (fixed, sample edilmedi)
        if getattr(mcmc_result, "period_err", None) in (None, 0.0):
            try:
                setattr(mcmc_result, "period_err", None)
            except Exception:
                pass

        logger.debug(
            f"MCMC harmonization tamamlandı — "
            f"baseline={getattr(mcmc_result, 'baseline', None)}, "
            f"log_jitter={getattr(mcmc_result, 'log_jitter', None)}, "
            f"a_over_rs={getattr(mcmc_result, 'a_over_rs', None)}"
        )

        return mcmc_result

    def _should_run_mcmc(self, candidate: CascadeCandidate) -> bool:
        """MCMC çalıştırılmalı mı karar verir."""

        if self.force_map or self._mcmc_fitter is None:
            return False

        if self.force_mcmc:
            return True

        if not self._mcmc_auto_upgrade:
            return False

        return candidate.snr >= self._mcmc_snr_threshold

    def fit(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
    ) -> "FitResult":
        """
        Transit adayını fit eder.

        MAP her zaman çalışır.
        MCMC sadece kurulu ve güçlü adaylarda uygulanır.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Trend giderilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.

        Returns
        -------
        MAPFitResult veya MCMCFitResult
            Fit sonuçları.
        """

        target_id = candidate.target_id
        sector = candidate.sector

        use_mcmc = self._should_run_mcmc(candidate)

        logger.info(
            f"Modelleme başlıyor — "
            f"{target_id} sektör {sector}: "
            f"SNR={candidate.snr:.2f}, "
            f"MCMC={'evet' if use_mcmc else 'hayır'}"
        )

        # Prior oluştur
        priors = TransitPriors.from_cascade(
            candidate,
            stellar_radius=self.stellar_radius,
            stellar_mass=self.stellar_mass,
            stellar_teff=self.stellar_teff,
        )

        # ── MAP Fit ──
        map_result = self._map_fitter.fit(
            detrended=detrended,
            priors=priors,
            stellar_radius=self.stellar_radius,
            stellar_mass=self.stellar_mass,
            stellar_teff=self.stellar_teff,
        )

        if not map_result.success:
            logger.warning(
                f"MAP fit başarısız — {target_id} sektör {sector}"
            )
            return map_result

        # ── MCMC Fit (koşullu) ──
        if use_mcmc and self._mcmc_fitter is not None:
            logger.info(
                f"MCMC yükseltmesi — "
                f"SNR={candidate.snr:.2f} ≥ eşik={self._mcmc_snr_threshold}"
            )

            try:
                mcmc_result = self._mcmc_fitter.fit(
                    detrended=detrended,
                    priors=priors,
                    map_result=map_result,
                    stellar_radius=self.stellar_radius,
                    stellar_mass=self.stellar_mass,
                    stellar_teff=self.stellar_teff,
                )

                if mcmc_result.success:
                    mcmc_result = self._harmonize_mcmc_result(
                        mcmc_result, map_result
                    )
                    logger.info(
                        f"MCMC sonucu kullanılıyor — "
                        f"{target_id} sektör {sector}"
                    )
                    return mcmc_result
                else:
                    logger.warning(
                        f"MCMC başarısız, MAP sonucu kullanılıyor — "
                        f"{target_id} sektör {sector}"
                    )
                    return map_result

            except Exception as e:
                logger.warning(
                    f"MCMC hatası, MAP kullanılıyor: {e}"
                )
                return map_result

        logger.info(
            f"MAP sonucu nihai — "
            f"{target_id} sektör {sector}"
        )

        return map_result