"""
Sinyal-Gürültü Oranı (SNR) hesaplama modülü.

Farklı SNR tanımlarını uygular ve karşılaştırır.

Kullanılan tanımlar:
    1. Basit SNR: transit_depth / noise_floor
    2. Dutycycle SNR: depth / (noise * sqrt(T_transit / T_obs))
    3. Per-point SNR: depth / (noise / sqrt(n_in_transit))
    4. TLS SNR: TLS'den gelen SNR değeri

Literatür:
    Pont et al. (2006)
    Kovacs et al. (2002)
    Hippke & Heller (2019)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.cascade import CascadeCandidate


@dataclass
class SNRBreakdown:
    """
    Farklı SNR hesaplama yöntemlerinin sonuçları.

    Attributes
    ----------
    snr_simple : float
        depth / noise (en basit tanım).
    snr_dutycycle : float
        Görev döngüsü düzeltmeli SNR.
    snr_per_point : float
        Nokta başına SNR.
    snr_tls : float
        TLS'den gelen SNR.
    snr_adopted : float
        Pipeline'ın benimsediği final SNR.
        TLS varsa TLS, yoksa dutycycle kullanılır.
    noise_floor_ppm : float
        Kullanılan gürültü tabanı (ppm).
    n_in_transit_total : int
        Transit içindeki toplam nokta sayısı.
    duty_cycle : float
        T_transit / T_orbit (görev döngüsü).
    """

    snr_simple: float = 0.0
    snr_dutycycle: float = 0.0
    snr_per_point: float = 0.0
    snr_tls: float = 0.0
    snr_adopted: float = 0.0
    noise_floor_ppm: float = 0.0
    n_in_transit_total: int = 0
    duty_cycle: float = 0.0

    def to_dict(self) -> dict:
        return {
            "snr_simple": round(self.snr_simple, 4),
            "snr_dutycycle": round(self.snr_dutycycle, 4),
            "snr_per_point": round(self.snr_per_point, 4),
            "snr_tls": round(self.snr_tls, 4),
            "snr_adopted": round(self.snr_adopted, 4),
            "noise_floor_ppm": round(self.noise_floor_ppm, 2),
            "n_in_transit_total": self.n_in_transit_total,
            "duty_cycle": round(self.duty_cycle, 6),
        }


class SNRCalculator:
    """
    Kapsamlı SNR hesaplayıcı.

    Parameters
    ----------
    cadence_sec : float
        Gözlem kadansı (saniye).
    """

    def __init__(self, cadence_sec: float = 120.0):
        self.cadence_sec = cadence_sec

    def compute(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
    ) -> SNRBreakdown:
        """
        Tüm SNR tanımlarını hesaplar.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.

        Returns
        -------
        SNRBreakdown
            Tüm SNR değerleri.
        """

        time = detrended.time
        flux = detrended.flux

        depth = candidate.depth
        duration = candidate.duration  # gün
        period = candidate.period      # gün
        n_transits = max(1, len(candidate.transit_times))

        # Gürültü tabanı (out-of-transit std)
        noise_floor = self._estimate_noise_floor(
            time, flux, candidate
        )
        noise_floor_ppm = noise_floor * 1e6

        # Görev döngüsü
        duty_cycle = duration / period if period > 0 else 0.0

        # Transit içindeki nokta sayısı (tek geçiş için)
        dt = float(np.nanmedian(np.diff(time))) if len(time) > 1 else self.cadence_sec / 86400
        n_per_transit = max(1, int(duration / dt))
        n_in_transit_total = n_per_transit * n_transits

        # ── SNR hesapları ──

        # 1. Basit SNR
        snr_simple = depth / noise_floor if noise_floor > 0 else 0.0

        # 2. Dutycycle SNR
        # SNR_dc = depth / noise × sqrt(n_in_transit / n_total)
        n_total = len(flux)
        if noise_floor > 0 and n_total > 0:
            snr_dutycycle = (depth / noise_floor) * np.sqrt(
                n_in_transit_total / n_total
            )
        else:
            snr_dutycycle = 0.0

        # 3. Per-point SNR
        if noise_floor > 0 and n_in_transit_total > 0:
            snr_per_point = depth / (noise_floor / np.sqrt(n_in_transit_total))
        else:
            snr_per_point = 0.0

        # 4. TLS SNR
        snr_tls = 0.0
        if candidate.tls_result is not None:
            snr_tls = float(candidate.tls_result.snr)

        # 5. Adopted SNR
        if snr_tls > 0:
            snr_adopted = snr_tls
        else:
            snr_adopted = snr_dutycycle

        logger.debug(
            f"SNR hesabı — "
            f"{candidate.target_id}: "
            f"basit={snr_simple:.2f}, "
            f"dutycycle={snr_dutycycle:.2f}, "
            f"TLS={snr_tls:.2f}, "
            f"adopted={snr_adopted:.2f}"
        )

        return SNRBreakdown(
            snr_simple=float(snr_simple),
            snr_dutycycle=float(snr_dutycycle),
            snr_per_point=float(snr_per_point),
            snr_tls=float(snr_tls),
            snr_adopted=float(snr_adopted),
            noise_floor_ppm=float(noise_floor_ppm),
            n_in_transit_total=int(n_in_transit_total),
            duty_cycle=float(duty_cycle),
        )

    def _estimate_noise_floor(
        self,
        time: np.ndarray,
        flux: np.ndarray,
        candidate: CascadeCandidate,
        window_factor: float = 3.0,
    ) -> float:
        """
        Transit dışı bölgelerden gürültü tabanını tahmin eder.

        Transit pencerelerini maskeler ve kalan
        bölgenin standart sapmasını hesaplar.

        Parameters
        ----------
        time : np.ndarray
            Zaman dizisi.
        flux : np.ndarray
            Flux dizisi.
        candidate : CascadeCandidate
            Cascade sonucu (transit zamanları için).
        window_factor : float
            Transit pencere genişliği = duration × window_factor.

        Returns
        -------
        float
            Gürültü tabanı (göreli birim).
        """

        half_window = candidate.duration * window_factor / 2.0

        # Transit maskesi oluştur
        in_transit = np.zeros(len(time), dtype=bool)

        for t_transit in candidate.transit_times:
            mask = np.abs(time - t_transit) < half_window
            in_transit |= mask

        out_of_transit = ~in_transit

        if out_of_transit.sum() < 20:
            # Yeterli OOT nokta yoksa tüm veriyi kullan
            return float(np.nanstd(flux - 1.0))

        oot_flux = flux[out_of_transit]
        return float(np.nanstd(oot_flux))