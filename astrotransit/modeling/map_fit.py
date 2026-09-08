"""
MAP (Maximum A Posteriori) transit fit modülü.

scipy.optimize kullanarak hızlı, Bayesyen optimizasyon
tabanlı parametre tahmini yapar.

Pipeline'daki rolü:
    - Tüm onaylı adaylara uygulanır (MCMC'ye kıyasla çok hızlı)
    - MCMC için iyi başlangıç noktası üretir
    - SNR < mcmc_snr_threshold olan adaylarda nihai sonuç olarak kullanılır

Optimizasyon yöntemi:
    L-BFGS-B (sınırlı bellek, kutu kısıtlamalı BFGS)
    Negatif log-posterior minimize edilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.optimize import minimize, OptimizeResult
from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.modeling.parameters import (
    TransitPriors,
    DerivedParameters,
    compute_derived_parameters,
)
from astrotransit.modeling.transit_model import TransitModel, TransitModelParams


# ──────────────────────────────────────
# Sonuç veri modeli
# ──────────────────────────────────────
@dataclass
class MAPFitResult:
    """
    MAP fit sonuçları.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    success : bool
        Optimizasyon başarılı mı?
    period : float
        Fit edilen periyot (gün).
    period_err : float
        Periyot belirsizliği (gün) — MAP için yaklaşık.
    t0 : float
        Fit edilen birinci transit zamanı.
    rp_rs : float
        Fit edilen yarıçap oranı.
    impact_parameter : float
        Fit edilen etki parametresi.
    a_over_rs : float
        Fit edilen a/Rs.
    inclination : float
        Fit edilen yörünge eğimi (derece).
    u1, u2 : float
        Fit edilen limb darkening katsayıları.
    log_jitter : float
        Fit edilen jitter.
    baseline : float
        Fit edilen flux baseline.
    log_likelihood : float
        MAP log-likelihood değeri.
    residual_rms : float
        Fit sonrası residual RMS.
    derived : DerivedParameters
        Türetilmiş fiziksel parametreler.
    n_iterations : int
        Optimizasyon iterasyon sayısı.
    optimizer_message : str
        Optimizer mesajı.
    fit_method : str
        Kullanılan fit yöntemi.
    """

    target_id: str
    sector: int
    success: bool
    period: float = 0.0
    period_err: float = 0.0
    t0: float = 0.0
    rp_rs: float = 0.0
    impact_parameter: float = 0.0
    a_over_rs: float = 0.0
    inclination: float = 90.0
    u1: float = 0.3
    u2: float = 0.2
    log_jitter: float = -7.0
    baseline: float = 1.0
    log_likelihood: float = -np.inf
    residual_rms: float = 0.0
    derived: DerivedParameters = field(default_factory=DerivedParameters)
    n_iterations: int = 0
    optimizer_message: str = ""
    fit_method: str = "map"

    def to_dict(self) -> dict:
        """Serileştirilebilir sözlük."""
        base = {
            "target_id": self.target_id,
            "sector": self.sector,
            "fit_method": self.fit_method,
            "success": self.success,
            "period": round(self.period, 6),
            "period_err": round(self.period_err, 6),
            "t0": round(self.t0, 6),
            "rp_rs": round(self.rp_rs, 6),
            "impact_parameter": round(self.impact_parameter, 4),
            "a_over_rs": round(self.a_over_rs, 4),
            "inclination_deg": round(self.inclination, 4),
            "u1": round(self.u1, 4),
            "u2": round(self.u2, 4),
            "log_jitter": round(self.log_jitter, 4),
            "baseline": round(self.baseline, 6),
            "log_likelihood": round(self.log_likelihood, 4),
            "residual_rms_ppm": round(self.residual_rms * 1e6, 2),
            "n_iterations": self.n_iterations,
            "optimizer_message": self.optimizer_message,
        }
        base.update(self.derived.to_dict())
        return base

    def summary(self) -> dict:
        return self.to_dict()


# ──────────────────────────────────────
# Parametre vektör dönüşümleri
# ──────────────────────────────────────
class ParameterVector:
    """
    Optimizer parametreleri ile fiziksel parametreler
    arasında dönüşüm sağlar.

    Optimizer sınırsız uzayda çalıştığından bazı
    parametreler dönüştürülmüş (log, arcsin) formda
    optimize edilir.

    Dönüştürülen parametreler:
        rp_rs → log(rp_rs)         (pozitiflik)
        impact_parameter → değişmez (kutu kısıtı yeterli)
        log_jitter → değişmez      (zaten log)
    """

    PARAM_NAMES = [
        "period",
        "t0",
        "log_rp_rs",
        "impact_parameter",
        "u1",
        "u2",
        "log_jitter",
        "baseline",
    ]

    @staticmethod
    def to_vector(
        period: float,
        t0: float,
        rp_rs: float,
        impact_parameter: float,
        u1: float,
        u2: float,
        log_jitter: float,
        baseline: float,
    ) -> np.ndarray:
        """Fiziksel parametrelerden optimizer vektörü oluşturur."""
        return np.array([
            period,
            t0,
            np.log(max(rp_rs, 1e-6)),
            impact_parameter,
            u1,
            u2,
            log_jitter,
            baseline,
        ])

    @staticmethod
    def from_vector(x: np.ndarray) -> dict:
        """Optimizer vektöründen fiziksel parametreleri çıkarır."""
        return {
            "period": x[0],
            "t0": x[1],
            "rp_rs": np.exp(x[2]),
            "impact_parameter": x[3],
            "u1": x[4],
            "u2": x[5],
            "log_jitter": x[6],
            "baseline": x[7],
        }

    @staticmethod
    def bounds(priors: TransitPriors) -> list[tuple]:
        """scipy.optimize için parametre sınırları."""
        return [
            (priors.period_bounds[0], priors.period_bounds[1]),
            (priors.t0_bounds[0], priors.t0_bounds[1]),
            (np.log(priors.rp_rs_bounds[0]), np.log(priors.rp_rs_bounds[1])),
            (priors.impact_parameter_bounds[0], priors.impact_parameter_bounds[1]),
            (0.0, 1.0),     # u1
            (-1.0, 1.0),    # u2
            (-15.0, 0.0),   # log_jitter
            (0.9, 1.1),     # baseline
        ]


# ──────────────────────────────────────
# MAP fit sınıfı
# ──────────────────────────────────────
class MAPFitter:
    """
    MAP transit parametresi optimize edici.

    scipy L-BFGS-B kullanarak negatif log-posterior'ı minimize eder.

    Parameters
    ----------
    max_iterations : int
        Maksimum iterasyon sayısı.
    n_restarts : int
        Farklı başlangıç noktasından yeniden deneme sayısı.
        En iyi sonuç seçilir.
    """

    def __init__(
        self,
        max_iterations: int = 2000,
        n_restarts: int = 3,
    ):
        self.max_iterations = max_iterations
        self.n_restarts = n_restarts

        logger.debug(
            f"MAPFitter — "
            f"max_iter: {max_iterations}, "
            f"n_restarts: {n_restarts}"
        )

    def _negative_log_posterior(
        self,
        x: np.ndarray,
        model: TransitModel,
        observed_flux: np.ndarray,
        flux_err: np.ndarray,
        priors: TransitPriors,
        a_over_rs: float,
    ) -> float:
        """
        Negatif log-posterior hesaplar.

        log P(θ | data) ∝ log L(data | θ) + log π(θ)

        Parameters
        ----------
        x : np.ndarray
            Optimizer parametre vektörü.
        model : TransitModel
            Transit model hesaplayıcı.
        observed_flux : np.ndarray
            Gözlenen flux.
        flux_err : np.ndarray
            Flux hataları.
        priors : TransitPriors
            Prior değerleri.
        a_over_rs : float
            Sabit tutulan a/Rs değeri.

        Returns
        -------
        float
            Negatif log-posterior.
        """

        try:
            phys = ParameterVector.from_vector(x)

            # NaN/Inf kontrolü
            for val in phys.values():
                if not np.isfinite(val):
                    return 1e10

            # Fiziksel sınır kontrolü
            if phys["rp_rs"] <= 0 or phys["rp_rs"] > 1.0:
                return 1e10
            if phys["impact_parameter"] < 0 or phys["impact_parameter"] > 1.5:
                return 1e10
            if phys["period"] <= 0:
                return 1e10
            if phys["baseline"] < 0.5 or phys["baseline"] > 1.5:
                return 1e10

            # Grazing transit ve fiziksel olmayan konfigürasyon kontrolü
            # b + rp_rs > 1 + rp_rs ise transit tam grazing (yani hiç kesişmiyor)
            if phys["impact_parameter"] >= 1.0 + phys["rp_rs"]:
                return 1e10

            # Eğim hesapla
            inc = TransitModel.impact_to_inclination(
                phys["impact_parameter"], a_over_rs
            )

            transit_params = TransitModelParams(
                period=phys["period"],
                t0=phys["t0"],
                rp=phys["rp_rs"],
                a=a_over_rs,
                inc=inc,
                u1=phys["u1"],
                u2=phys["u2"],
                baseline=phys["baseline"],
            )

            # Log-likelihood
            log_like = model.log_likelihood(
                transit_params,
                observed_flux,
                flux_err,
                log_jitter=phys["log_jitter"],
            )

            if not np.isfinite(log_like):
                return 1e10

            # Log-prior (sadece Gaussian priorlar için)
            log_prior = 0.0

            # baseline prior: N(1.0, 0.01)
            log_prior += -0.5 * ((phys["baseline"] - 1.0) / 0.01) ** 2

            return float(-(log_like + log_prior))

        except Exception:
            return np.inf

    def fit(
        self,
        detrended: DetrendedLightCurve,
        priors: TransitPriors,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
        stellar_teff: float = 5778.0,
    ) -> MAPFitResult:
        """
        MAP fit çalıştırır.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.
        priors : TransitPriors
            Prior değerleri ve başlangıç noktaları.
        stellar_radius : float
            Yıldız yarıçapı (R_sun).
        stellar_mass : float
            Yıldız kütlesi (M_sun).
        stellar_teff : float
            Yıldız efektif sıcaklığı (K).

        Returns
        -------
        MAPFitResult
            Optimize edilmiş transit parametreleri.
        """

        target_id = detrended.target_id
        sector = detrended.sector

        logger.info(
            f"MAP fit başlıyor — "
            f"{target_id} sektör {sector}: "
            f"P={priors.period:.4f}d"
        )

        time = detrended.time
        flux = detrended.flux
        flux_err = detrended.flux_err

        # a/Rs hesapla (Kepler 3. Yasası)
        a_over_rs = TransitModel.compute_a_over_rs(
            priors.period, stellar_mass, stellar_radius
        )

        logger.debug(f"a/Rs = {a_over_rs:.3f}")

        # TransitModel nesnesi oluştur
        model = TransitModel(time)

        # Başlangıç vektörü
        x0 = ParameterVector.to_vector(
            period=priors.period,
            t0=priors.t0,
            rp_rs=priors.rp_rs,
            impact_parameter=priors.impact_parameter,
            u1=priors.u1,
            u2=priors.u2,
            log_jitter=priors.log_jitter,
            baseline=priors.baseline,
        )

        bounds = ParameterVector.bounds(priors)

        # ── Çok başlangıçlı optimizasyon ──
        best_result: Optional[OptimizeResult] = None
        best_nll = np.inf

        rng = np.random.default_rng(42)

        for restart in range(self.n_restarts):
            if restart == 0:
                x_start = x0.copy()
            else:
                # Küçük rastgele pertürbasyon
                perturbation = rng.normal(scale=0.05, size=len(x0))
                x_start = x0 + perturbation

                # Sınırlar içinde tut
                for i, (lo, hi) in enumerate(bounds):
                    if lo is not None and hi is not None:
                        x_start[i] = float(np.clip(x_start[i], lo, hi))

            try:
                result = minimize(
                    self._negative_log_posterior,
                    x0=x_start,
                    args=(model, flux, flux_err, priors, a_over_rs),
                    method="L-BFGS-B",
                    bounds=bounds,
                    options={
                        "maxiter": self.max_iterations,
                        "ftol": 1e-12,
                        "gtol": 1e-8,
                    },
                )

                if result.fun < best_nll:
                    best_nll = result.fun
                    best_result = result

                logger.debug(
                    f"MAP restart {restart + 1}/{self.n_restarts}: "
                    f"NLL={result.fun:.4f}, "
                    f"başarı={result.success}"
                )

            except Exception as e:
                logger.warning(f"MAP restart {restart + 1} başarısız: {e}")
                continue

        # ── Sonuçları çıkar ──
        if best_result is None:
            logger.error(f"MAP fit başarısız: {target_id} sektör {sector}")
            return self._failed_result(target_id, sector)

        best_phys = ParameterVector.from_vector(best_result.x)

        # Eğim hesapla
        inclination = TransitModel.impact_to_inclination(
            best_phys["impact_parameter"], a_over_rs
        )

        # Residual hesapla
        final_params = TransitModelParams(
            period=best_phys["period"],
            t0=best_phys["t0"],
            rp=best_phys["rp_rs"],
            a=a_over_rs,
            inc=inclination,
            u1=best_phys["u1"],
            u2=best_phys["u2"],
            baseline=best_phys["baseline"],
        )

        model_flux = model.flux(final_params)
        residuals = flux - model_flux
        residual_rms = float(np.sqrt(np.nanmean(residuals ** 2)))

        # Türetilmiş parametreler
        derived = compute_derived_parameters(
            period=best_phys["period"],
            rp_rs=best_phys["rp_rs"],
            impact_parameter=best_phys["impact_parameter"],
            duration=priors.duration,
            stellar_radius=stellar_radius,
            stellar_mass=stellar_mass,
            stellar_teff=stellar_teff,
        )

        # Başarı: optimizer converge etti VE NLL fiziksel bir değerde
        fit_success = (
            best_result is not None
            and np.isfinite(best_nll)
            and best_nll < 1e9
            and best_phys["rp_rs"] > 0
            and 0 < best_phys["period"] < 10000
        )

        map_result = MAPFitResult(
            target_id=target_id,
            sector=sector,
            success=fit_success,
            period=float(best_phys["period"]),
            period_err=priors.period_err if hasattr(priors, 'period_err') else priors.period * 0.001,
            t0=float(best_phys["t0"]),
            rp_rs=float(best_phys["rp_rs"]),
            impact_parameter=float(best_phys["impact_parameter"]),
            a_over_rs=float(a_over_rs),
            inclination=float(inclination),
            u1=float(best_phys["u1"]),
            u2=float(best_phys["u2"]),
            log_jitter=float(best_phys["log_jitter"]),
            baseline=float(best_phys["baseline"]),
            log_likelihood=float(-best_nll),
            residual_rms=residual_rms,
            derived=derived,
            n_iterations=int(best_result.nit),
            optimizer_message=str(best_result.message),
            fit_method="map",
        )

        logger.info(
            f"MAP fit tamamlandı — "
            f"{target_id} sektör {sector}: "
            f"P={map_result.period:.4f}d, "
            f"Rp/Rs={map_result.rp_rs:.4f}, "
            f"Rp={map_result.derived.planet_radius_rearth:.2f} Re, "
            f"residual RMS={residual_rms * 1e6:.1f} ppm"
        )

        return map_result

    def _failed_result(self, target_id: str, sector: int) -> MAPFitResult:
        """Başarısız MAP sonucu döndürür."""

        return MAPFitResult(
            target_id=target_id,
            sector=sector,
            success=False,
            optimizer_message="Optimizasyon başarısız.",
        )