"""
Transit ışık eğrisi modeli.

Mandel & Agol (2002) quadratic limb darkening transit modelini
kullanarak normalize flux değerleri üretir.

Kullanılan kütüphane: batman-package
Alternatif: exoplanet (PyMC entegrasyonu için ayrı modülde)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from loguru import logger

try:
    import batman
    _BATMAN_AVAILABLE = True
except ImportError as _batman_import_error:
    _BATMAN_AVAILABLE = False
    # Gerçek hata mesajını kaydet: sessiz devre-dışı bırakma, ortam
    # sorunlarını (eksik/başarısız kurulum, sürüm uyumsuzluğu) gizler.
    logger.warning(
        "batman-package yüklenemedi — transit modeli devre dışı "
        f"(pip install batman-package). Sebep: {_batman_import_error}"
    )


@dataclass
class TransitModelParams:
    """
    batman transit model parametreleri.

    Attributes
    ----------
    period : float
        Orbital periyot (gün).
    t0 : float
        Birinci transit merkez zamanı.
    rp : float
        Yarıçap oranı Rp/Rs.
    a : float
        Yarı-büyük eksen Rs cinsinden (a/Rs).
    inc : float
        Yörünge eğimi (derece).
    ecc : float
        Eksentriklik (dairesel yörünge için 0).
    w : float
        Argüman of periastron (derece).
    u1, u2 : float
        Quadratic limb darkening katsayıları.
    baseline : float
        Flux baseline (normalde 1.0).
    """

    period: float
    t0: float
    rp: float
    a: float
    inc: float = 90.0
    ecc: float = 0.0
    w: float = 90.0
    u1: float = 0.3
    u2: float = 0.2
    baseline: float = 1.0

    def to_batman_params(self) -> "batman.TransitParams":
        """batman.TransitParams nesnesine dönüştürür."""

        if not _BATMAN_AVAILABLE:
            raise ImportError("batman-package gereklidir.")

        params = batman.TransitParams()
        params.per = self.period
        params.t0 = self.t0
        params.rp = self.rp
        params.a = self.a
        params.inc = self.inc
        params.ecc = self.ecc
        params.w = self.w
        params.u = [self.u1, self.u2]
        params.limb_dark = "quadratic"

        return params


class TransitModel:
    """
    batman transit model hesaplayıcı.

    Verilen parametreler için transit ışık eğrisi üretir.
    MAP fit ve MCMC likelihood hesaplamalarında kullanılır.

    Parameters
    ----------
    time : np.ndarray
        Zaman dizisi (parametrelerle aynı birimde).
    """

    def __init__(self, time: np.ndarray):
        if not _BATMAN_AVAILABLE:
            raise ImportError("batman-package gereklidir: pip install batman-package")

        self.time = time
        self._model = None
        self._last_params = None

        logger.debug(f"TransitModel oluşturuldu — {len(time)} zaman noktası")

    def _init_model(self, params: TransitModelParams) -> None:
        """batman modelini ilk kez başlatır."""

        batman_params = params.to_batman_params()
        self._model = batman.TransitModel(batman_params, self.time)
        self._last_params = params

    def flux(self, params: TransitModelParams) -> np.ndarray:
        """
        Verilen parametreler için model flux dizisi üretir.

        Parameters
        ----------
        params : TransitModelParams
            Transit model parametreleri.

        Returns
        -------
        np.ndarray
            Model flux değerleri (aynı boyutta self.time ile).
        """

        batman_params = params.to_batman_params()

        # İlk kez ise modeli başlat, sonra light_curve çağır
        if self._model is None:
            self._model = batman.TransitModel(batman_params, self.time)

        # batman.TransitModel.light_curve() her çağrıda yeni parametrelerle çalışır
        model_flux = self._model.light_curve(batman_params)
        return model_flux * params.baseline

    def residuals(
        self,
        params: TransitModelParams,
        observed_flux: np.ndarray,
    ) -> np.ndarray:
        """
        Gözlenen ve model flux arasındaki farkı döndürür.

        Parameters
        ----------
        params : TransitModelParams
            Model parametreleri.
        observed_flux : np.ndarray
            Gözlenen flux dizisi.

        Returns
        -------
        np.ndarray
            Residual dizisi (gözlenen - model).
        """

        model = self.flux(params)
        return observed_flux - model

    def log_likelihood(
        self,
        params: TransitModelParams,
        observed_flux: np.ndarray,
        flux_err: np.ndarray,
        log_jitter: float = -15.0,
    ) -> float:
        """
        Gaussian log-likelihood hesaplar.

        L = -0.5 × Σ [(r²/σ²) + log(2π σ²)]
        σ² = flux_err² + jitter²

        Parameters
        ----------
        params : TransitModelParams
            Model parametreleri.
        observed_flux : np.ndarray
            Gözlenen flux.
        flux_err : np.ndarray
            Flux hataları.
        log_jitter : float
            Log ek gürültü terimi.

        Returns
        -------
        float
            Sayısal olarak normalize edilmiş (sabit ofseti alınmış)
            log-likelihood değeri.

        Notes
        -----
        Gaussian yoğunlukları, flux birimleri küçük olduğunda pozitif
        mutlak log değerleri üretebilir.  Bu, özellikle normalized light
        curve'lerde karşılaştırmayı zorlaştırır ve eski downstream çıktılar
        negatif log-likelihood varsayar.  Burada parametrelerden bağımsız,
        jitter=0 durumundaki hata-normalizasyon sabitini çıkarıyoruz.
        Böylece optimizasyon sıralaması değişmez; yalnızca raporlanan değer
        sabit bir referansa göre verilir.
        """

        observed_flux = np.asarray(observed_flux, dtype=float)
        flux_err = np.asarray(flux_err, dtype=float)
        if observed_flux.shape != flux_err.shape:
            raise ValueError("observed_flux ve flux_err aynı boyutta olmalıdır.")
        if not np.all(np.isfinite(observed_flux)) or not np.all(np.isfinite(flux_err)):
            raise ValueError("observed_flux ve flux_err sonlu değerlerden oluşmalıdır.")
        if np.any(flux_err <= 0):
            raise ValueError("flux_err değerleri pozitif olmalıdır.")
        if not np.isfinite(log_jitter):
            raise ValueError("log_jitter sonlu olmalıdır.")

        jitter = np.exp(log_jitter)
        sigma2 = flux_err ** 2 + jitter ** 2

        resid = self.residuals(params, observed_flux)

        raw_log_like = -0.5 * np.sum(
            resid ** 2 / sigma2 + np.log(2 * np.pi * sigma2)
        )

        # This is a data-only constant.  It keeps the peak at or below zero
        # without changing MAP/MCMC comparisons between model parameters.
        reference = np.sum(
            np.maximum(0.0, -0.5 * np.log(2 * np.pi * flux_err ** 2))
        )
        return float(raw_log_like - reference)

    @staticmethod
    def impact_to_inclination(
        impact_parameter: float,
        a_over_rs: float,
    ) -> float:
        """
        Etki parametresini yörünge eğimine dönüştürür.

        i = arccos(b / (a/Rs))

        Parameters
        ----------
        impact_parameter : float
            Etki parametresi b.
        a_over_rs : float
            Yarı-büyük eksen / yıldız yarıçapı.

        Returns
        -------
        float
            Yörünge eğimi (derece).
        """

        if a_over_rs <= 0:
            return 90.0

        cos_i = impact_parameter / a_over_rs
        cos_i = float(np.clip(cos_i, -1.0, 1.0))
        return float(np.degrees(np.arccos(cos_i)))

    @staticmethod
    def compute_a_over_rs(
        period: float,
        stellar_mass: float,
        stellar_radius: float,
    ) -> float:
        """
        Kepler 3. Yasası'ndan a/Rs hesaplar.

        a/Rs = (G M* P² / 4π² Rs³)^(1/3)

        Parameters
        ----------
        period : float
            Orbital periyot (gün).
        stellar_mass : float
            Yıldız kütlesi (M_sun).
        stellar_radius : float
            Yıldız yarıçapı (R_sun).

        Returns
        -------
        float
            a/Rs değeri.
        """

        from astrotransit.modeling.parameters import CONST

        period_s = period * 86400.0
        m_star_kg = stellar_mass * CONST.M_SUN
        r_star_m = stellar_radius * CONST.R_SUN

        try:
            a_m = (CONST.G * m_star_kg * period_s ** 2 / (4 * np.pi ** 2)) ** (1.0 / 3.0)
            return float(a_m / r_star_m)
        except (ValueError, ZeroDivisionError):
            return 15.0