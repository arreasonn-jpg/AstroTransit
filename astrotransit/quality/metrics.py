"""
Transit kalite metrikleri hesaplama modülü.

Her transit adayı için bilimsel kalite göstergelerini
hesaplar. Bu metrikler hem filtreleme hem de
kategorizasyon aşamasında kullanılır.

Literatür referansları:
    Jenkins et al. (2002) — TESS Data Products
    Pont et al. (2006)    — Systematic effects in LC fitting
    Burke et al. (2015)   — Kepler Planet Occurrence Rates
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from loguru import logger
from scipy import stats as scipy_stats

from astrotransit.detection.cascade import CascadeCandidate
from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve


# ──────────────────────────────────────
# Fotometrik kalite metrikleri
# ──────────────────────────────────────
@dataclass
class PhotometricMetrics:
    """
    Ham ışık eğrisinin fotometrik kalite metrikleri.

    Attributes
    ----------
    flux_rms : float
        Flux standart sapması.
    median_flux : float
        Medyan flux değeri.
    noise_ppm : float
        Gürültü seviyesi (ppm).
    cdpp_1hr : float
        Combined Differential Photometric Precision (1 saat).
    data_completeness : float
        Veri tamlığı (0-1).
    n_points : int
        Temiz veri noktası sayısı.
    n_gaps : int
        Veri boşluğu sayısı.
    skewness : float
        Flux dağılımı çarpıklığı.
    kurtosis : float
        Flux dağılımı basıklığı.
    variance : float
        Flux varyansı.
    entropy : float
        Flux Shannon entropisi (aykırı değer göstergesi).
    """

    flux_rms: float = 0.0
    median_flux: float = 0.0
    noise_ppm: float = 0.0
    cdpp_1hr: float = 0.0
    data_completeness: float = 0.0
    n_points: int = 0
    n_gaps: int = 0
    skewness: float = 0.0
    kurtosis: float = 0.0
    variance: float = 0.0
    entropy: float = 0.0

    def to_dict(self) -> dict:
        return {
            "flux_rms": round(self.flux_rms, 8),
            "median_flux": round(self.median_flux, 6),
            "noise_ppm": round(self.noise_ppm, 2),
            "cdpp_1hr_ppm": round(self.cdpp_1hr, 2),
            "data_completeness": round(self.data_completeness, 4),
            "n_points": self.n_points,
            "n_gaps": self.n_gaps,
            "skewness": round(self.skewness, 4),
            "kurtosis": round(self.kurtosis, 4),
            "variance": round(self.variance, 10),
            "entropy": round(self.entropy, 4),
        }


@dataclass
class TransitMetrics:
    """
    Transit sinyalinin kalite metrikleri.

    Attributes
    ----------
    snr : float
        Sinyal-gürültü oranı.
    transit_depth : float
        Transit derinliği (göreli birim).
    transit_depth_ppm : float
        Transit derinliği (ppm).
    transit_duration_hours : float
        Transit süresi (saat).
    period : float
        Orbital periyot (gün).
    n_transits : int
        Gözlemlenen transit sayısı.
    transit_symmetry : float
        Transit simetri skoru (0-1, 1=mükemmel).
    ingress_egress_ratio : float
        Giriş/çıkış süresi oranı (1.0 = simetrik).
    depth_variance : float
        Bireysel transit derinlikleri arasındaki varyans.
    timing_rms : float
        Transit zamanlama residual RMS (TTV göstergesi).
    odd_even_mismatch : float
        Tek-çift transit derinlik farkı (sigma).
    residual_rms : float
        Model sonrası residual RMS.
    """

    snr: float = 0.0
    transit_depth: float = 0.0
    transit_depth_ppm: float = 0.0
    transit_duration_hours: float = 0.0
    period: float = 0.0
    n_transits: int = 0
    transit_symmetry: float = 0.0
    ingress_egress_ratio: float = 1.0
    depth_variance: float = 0.0
    timing_rms: float = 0.0
    odd_even_mismatch: float = 0.0
    residual_rms: float = 0.0
    shape_correlation: float = 0.0
    odd_even_harmonic: float = 0.0

    def to_dict(self) -> dict:
        return {
            "snr": round(self.snr, 4),
            "transit_depth": round(self.transit_depth, 8),
            "transit_depth_ppm": round(self.transit_depth_ppm, 2),
            "transit_duration_hours": round(self.transit_duration_hours, 4),
            "period_days": round(self.period, 6),
            "n_transits": self.n_transits,
            "transit_symmetry": round(self.transit_symmetry, 4),
            "ingress_egress_ratio": round(self.ingress_egress_ratio, 4),
            "depth_variance": round(self.depth_variance, 8),
            "timing_rms_min": round(self.timing_rms * 1440, 4),
            "odd_even_mismatch": round(self.odd_even_mismatch, 4),
            "residual_rms_ppm": round(self.residual_rms * 1e6, 2),
            "shape_correlation": round(self.shape_correlation, 4),
            "odd_even_harmonic": round(self.odd_even_harmonic, 4),
        }

@dataclass
class StellarMetrics:
    """
    Yıldız kaynaklı kalite metrikleri.

    Attributes
    ----------
    is_variable_star : bool
        Değişen yıldız işareti.
    variability_amplitude : float
        Değişkenlik genliği (ppm).
    rotation_period_days : float
        Tahmini yıldız dönüş periyodu (gün). 0 = tespit edilemedi.
    lomb_scargle_peak : float
        Lomb-Scargle periodogram tepe gücü.
    lomb_scargle_period : float
        Lomb-Scargle en güçlü periyot (gün).
    is_binary_suspect : bool
        İkili yıldız şüphesi.
    secondary_eclipse_depth : float
        İkincil tutulma derinliği. 0 = tespit edilmedi.
    centroid_shift : float
        Centroid kayması. Büyük değer = arka plan EB şüphesi.
    """

    is_variable_star: bool = False
    variability_amplitude: float = 0.0
    rotation_period_days: float = 0.0
    lomb_scargle_peak: float = 0.0
    lomb_scargle_period: float = 0.0
    is_binary_suspect: bool = False
    secondary_eclipse_depth: float = 0.0
    secondary_eclipse_snr: float = 0.0
    centroid_shift: float = 0.0

    def to_dict(self) -> dict:
        return {
            "is_variable_star": self.is_variable_star,
            "variability_amplitude_ppm": round(self.variability_amplitude, 2),
            "rotation_period_days": round(self.rotation_period_days, 4),
            "lomb_scargle_peak": round(self.lomb_scargle_peak, 4),
            "lomb_scargle_period_days": round(self.lomb_scargle_period, 4),
            "is_binary_suspect": self.is_binary_suspect,
            "secondary_eclipse_depth_ppm": round(self.secondary_eclipse_depth * 1e6, 2),
            "secondary_eclipse_snr": round(self.secondary_eclipse_snr, 4),
            "centroid_shift": round(self.centroid_shift, 4),
        }


@dataclass
class QualityMetrics:
    """
    Tüm kalite metriklerini bir arada tutan ana nesne.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    photometric : PhotometricMetrics
        Fotometrik kalite metrikleri.
    transit : TransitMetrics
        Transit kalite metrikleri.
    stellar : StellarMetrics
        Yıldız kaynaklı metrikler.
    """

    target_id: str
    sector: int
    photometric: PhotometricMetrics = field(default_factory=PhotometricMetrics)
    transit: TransitMetrics = field(default_factory=TransitMetrics)
    stellar: StellarMetrics = field(default_factory=StellarMetrics)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "photometric": self.photometric.to_dict(),
            "transit": self.transit.to_dict(),
            "stellar": self.stellar.to_dict(),
        }


# ──────────────────────────────────────
# Metrik hesaplayıcı
# ──────────────────────────────────────
class QualityMetricsCalculator:
    """
    Transit adayı için kalite metriklerini hesaplar.

    Parameters
    ----------
    cadence_sec : float
        Gözlem kadansı (saniye). CDPP hesabı için gerekli.
    """

    def __init__(self, cadence_sec: float = 120.0):
        self.cadence_sec = cadence_sec

        logger.debug(
            f"QualityMetricsCalculator — kadans: {cadence_sec}s"
        )

    def compute_photometric(
        self,
        detrended: DetrendedLightCurve,
    ) -> PhotometricMetrics:
        """
        Fotometrik kalite metriklerini hesaplar.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.

        Returns
        -------
        PhotometricMetrics
        """

        flux = detrended.flux
        time = detrended.time

        if len(flux) < 10:
            logger.warning("Çok az nokta: fotometrik metrik hesaplanamıyor.")
            return PhotometricMetrics()

        # Temel istatistikler
        flux_rms = float(np.nanstd(flux - 1.0))
        median_flux = float(np.nanmedian(flux))
        noise_ppm = flux_rms * 1e6
        variance = float(np.nanvar(flux))

        # CDPP (Combined Differential Photometric Precision)
        # 1 saatlik binlenmiş standart sapma
        cdpp_1hr = self._compute_cdpp(flux, time, bin_hours=1.0)

        # Veri tamlığı
        dt_median = float(np.nanmedian(np.diff(time)))
        expected_points = (time[-1] - time[0]) / dt_median if dt_median > 0 else len(time)
        completeness = min(1.0, len(time) / expected_points) if expected_points > 0 else 0.0

        # Boşluk sayısı
        gaps = np.where(np.diff(time) > 5 * dt_median)[0]
        n_gaps = len(gaps)

        # Dağılım özellikleri
        residual = flux - 1.0
        skewness = float(scipy_stats.skew(residual[np.isfinite(residual)]))
        kurtosis = float(scipy_stats.kurtosis(residual[np.isfinite(residual)]))

        # Shannon entropisi (aykırı değer göstergesi)
        entropy = self._compute_entropy(flux)

        return PhotometricMetrics(
            flux_rms=flux_rms,
            median_flux=median_flux,
            noise_ppm=noise_ppm,
            cdpp_1hr=cdpp_1hr,
            data_completeness=float(completeness),
            n_points=len(flux),
            n_gaps=n_gaps,
            skewness=skewness,
            kurtosis=kurtosis,
            variance=variance,
            entropy=entropy,
        )

    def compute_transit(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
        fit_result=None,
    ) -> TransitMetrics:
        """
        Transit kalite metriklerini hesaplar.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        fit_result : MAPFitResult veya MCMCFitResult, opsiyonel
            Fit sonucu (varsa residual ve daha hassas parametreler için).

        Returns
        -------
        TransitMetrics
        """

        tls = candidate.tls_result

        snr = candidate.snr
        depth = candidate.depth
        duration = candidate.duration
        period = candidate.period
        n_transits = len(candidate.transit_times)

        # Transit simetri skoru
        symmetry = 0.0
        ingress_egress_ratio = 1.0

        if tls is not None and len(tls.folded_flux) > 10:
            symmetry = self._compute_transit_symmetry(
                tls.folded_phase, tls.folded_flux
            )

        # Faz-derinlik korelasyonu (V-şekli EB göstergesi, adaptif pencere)
        shape_correlation = 0.0
        if tls is not None and len(tls.folded_flux) > 10:
            shape_correlation = self._compute_shape_correlation(
                tls.folded_phase, tls.folded_flux,
                duration=duration, period=period,
            )

        # Harmonik odd/even (ham veriden, EB göstergesi)
        odd_even_harmonic = 0.0
        if duration > 0 and period > 0:
            odd_even_harmonic = self._compute_harmonic_odd_even(
                detrended.time, detrended.flux, period, candidate.t0, duration
            )

        # Bireysel transit derinlikleri arasındaki varyans
        depth_variance = 0.0
        if tls is not None and len(tls.transit_depths) > 1:
            depth_variance = float(np.var(tls.transit_depths))

        # Transit zamanlama residual (TTV göstergesi)
        timing_rms = 0.0
        if tls is not None and len(tls.transit_times) > 2:
            timing_rms = self._compute_timing_rms(
                tls.transit_times, period
            )

        # Odd-even mismatch
        odd_even = 0.0
        if tls is not None:
            odd_even = float(tls.odd_even_mismatch)

        # Residual RMS (fit sonucundan)
        residual_rms = 0.0
        if fit_result is not None and hasattr(fit_result, 'residual_rms'):
            residual_rms = float(fit_result.residual_rms)

        return TransitMetrics(
            snr=float(snr),
            transit_depth=float(depth),
            transit_depth_ppm=float(depth * 1e6),
            transit_duration_hours=float(duration * 24),
            period=float(period),
            n_transits=n_transits,
            transit_symmetry=float(symmetry),
            ingress_egress_ratio=float(ingress_egress_ratio),
            depth_variance=float(depth_variance),
            timing_rms=float(timing_rms),
            odd_even_mismatch=float(odd_even),
            residual_rms=float(residual_rms),
            shape_correlation=float(shape_correlation),
            odd_even_harmonic=float(odd_even_harmonic),
        )

    def compute_stellar(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
    ) -> StellarMetrics:
        """
        Yıldız kaynaklı kalite metriklerini hesaplar.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.

        Returns
        -------
        StellarMetrics
        """

        time = detrended.time
        flux = detrended.flux

        # Lomb-Scargle periodogram (yıldız dönüşü / değişkenlik)
        ls_period, ls_power = self._lomb_scargle_peak(time, flux)

        # Değişkenlik genliği
        variability_amplitude = float(
            (np.nanpercentile(flux, 95) - np.nanpercentile(flux, 5)) * 1e6
        )

        # Değişen yıldız tespiti
        # Yüksek Lomb-Scargle gücü + transit periyodundan farklı periyot
        is_variable = (
            ls_power > 0.3 and
            abs(ls_period - candidate.period) / candidate.period > 0.05
        )

        # İkili yıldız şüphesi (odd-even mismatch yüksekse)
        is_binary_suspect = False
        if candidate.tls_result is not None:
            is_binary_suspect = (
                candidate.tls_result.odd_even_mismatch > 3.0
            )

        # İkincil tutulma tespiti
        secondary_depth = self._check_secondary_eclipse(
            time, flux, candidate.period, candidate.t0
        )

        # İkincil tutulma SNR (EB / odd-even alternation göstergesi)
        secondary_snr = self._compute_secondary_eclipse_snr(
            time, flux, candidate.period, candidate.t0, candidate.duration
        )

        return StellarMetrics(
            is_variable_star=is_variable,
            variability_amplitude=variability_amplitude,
            rotation_period_days=float(ls_period),
            lomb_scargle_peak=float(ls_power),
            lomb_scargle_period=float(ls_period),
            is_binary_suspect=is_binary_suspect,
            secondary_eclipse_depth=float(secondary_depth),
            secondary_eclipse_snr=float(secondary_snr),
            centroid_shift=0.0,
        )

    def compute_all(
        self,
        detrended: DetrendedLightCurve,
        candidate: CascadeCandidate,
        fit_result=None,
    ) -> QualityMetrics:
        """
        Tüm kalite metriklerini hesaplar.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.
        candidate : CascadeCandidate
            Cascade tespit sonucu.
        fit_result : opsiyonel
            Fit sonucu.

        Returns
        -------
        QualityMetrics
            Tüm metrikler.
        """

        logger.info(
            f"Kalite metrikleri hesaplanıyor — "
            f"{candidate.target_id} sektör {candidate.sector}"
        )

        photometric = self.compute_photometric(detrended)
        transit = self.compute_transit(detrended, candidate, fit_result)
        stellar = self.compute_stellar(detrended, candidate)

        metrics = QualityMetrics(
            target_id=candidate.target_id,
            sector=candidate.sector,
            photometric=photometric,
            transit=transit,
            stellar=stellar,
        )

        logger.info(
            f"Metrik hesaplama tamamlandı — "
            f"{candidate.target_id}: "
            f"SNR={transit.snr:.2f}, "
            f"gürültü={photometric.noise_ppm:.1f}ppm, "
            f"tamlık={photometric.data_completeness:.1%}"
        )

        return metrics

    # ──────────────────────────────────────
    # Yardımcı hesaplama metodları
    # ──────────────────────────────────────

    def _compute_cdpp(
        self,
        flux: np.ndarray,
        time: np.ndarray,
        bin_hours: float = 1.0,
    ) -> float:
        """
        CDPP (Combined Differential Photometric Precision) hesaplar.

        Belirtilen süre boyunca binlenmiş flux'un standart sapması.

        Parameters
        ----------
        flux : np.ndarray
            Normalize flux dizisi.
        time : np.ndarray
            Zaman dizisi (gün).
        bin_hours : float
            Bin süresi (saat).

        Returns
        -------
        float
            CDPP (ppm).
        """

        bin_days = bin_hours / 24.0
        dt = float(np.nanmedian(np.diff(time)))

        if dt <= 0:
            return 0.0

        points_per_bin = max(1, int(bin_days / dt))

        if points_per_bin >= len(flux):
            return float(np.nanstd(flux - 1.0) * 1e6)

        n_bins = len(flux) // points_per_bin
        if n_bins < 2:
            return float(np.nanstd(flux - 1.0) * 1e6)

        trimmed = flux[:n_bins * points_per_bin]
        binned = trimmed.reshape(n_bins, points_per_bin).mean(axis=1)

        return float(np.nanstd(binned) * 1e6)

    @staticmethod
    def _compute_entropy(flux: np.ndarray, n_bins: int = 50) -> float:
        """
        Flux dağılımının Shannon entropisi.

        Aykırı değerlerin varlığını gösterir.
        Düşük entropi = dağılım dar ve düzenli.
        Yüksek entropi = dağılım geniş veya çok modlu.
        """

        clean = flux[np.isfinite(flux)]

        if len(clean) < 10:
            return 0.0

        counts, _ = np.histogram(clean, bins=n_bins, density=True)
        counts = counts[counts > 0]

        if len(counts) == 0:
            return 0.0

        probs = counts / counts.sum()
        return float(-np.sum(probs * np.log(probs + 1e-10)))

    @staticmethod
    def _compute_shape_correlation(
        phase: np.ndarray,
        flux: np.ndarray,
        duration: float = 0.0,
        period: float = 0.0,
    ) -> float:
        """
        Faz mesafesi ile derinlik arasındaki Pearson korelasyonu (adaptif pencere).

        V-şekilli EB'de derinlik faz merkezinden uzaklaştıkça doğrusal
        azalır -> güçlü negatif korelasyon (r < -0.7).
        Kutu (gezegen) profilinde derinlik sabit -> r ~ 0.

        Pencere transit süresine göre adapte edilir; aksi halde uzun
        periyotlu EB'lerde baseline noktaları korelasyonu sulandırır.

        Returns
        -------
        float
            Pearson r; hesaplanamıyorsa 0.0.
        """

        if len(phase) < 20 or len(flux) < 20:
            return 0.0

        phase = np.asarray(phase, dtype=float)
        flux = np.asarray(flux, dtype=float)
        if np.isnan(flux).all() or np.isnan(phase).all():
            return 0.0

        try:
            center = float(phase[np.nanargmin(flux)])
        except (ValueError, IndexError):
            return 0.0

        dist = np.abs(phase - center)
        dist = np.minimum(dist, np.abs(dist - 1.0))

        if duration > 0 and period > 0:
            half_dur_phase = 0.5 * duration / period
            window = max(0.012, min(1.3 * half_dur_phase, 0.10))
        else:
            window = 0.06

        in_transit = dist < window
        out_transit = (dist > 2.5 * window) & (dist < 0.4)

        if in_transit.sum() < 6 or out_transit.sum() < 20:
            return 0.0

        baseline = float(np.median(flux[out_transit]))
        depth = baseline - flux[in_transit]
        d_dist = dist[in_transit]

        if depth.std() < 1e-9 or d_dist.std() < 1e-9:
            return 0.0

        try:
            r, _ = scipy_stats.pearsonr(d_dist, depth)
        except Exception:
            return 0.0

        if not np.isfinite(r):
            return 0.0
        return float(r)

    @staticmethod
    def _compute_harmonic_odd_even(
        time: np.ndarray,
        flux: np.ndarray,
        period: float,
        t0: float,
        duration: float,
    ) -> float:
        """
        P, P/2, 2P periyotlarında ham veriden tek/çift derinlik farkını ölçer.

        Cascade harmonik periyodu seçtiğinde odd/even sinyali silinebilir;
        bu metot üç katlamada en yüksek farkı döndürerek sinyali kurtarır.

        Returns
        -------
        float
            Maksimum bağıl tek/çift farkı (0-1); hesaplanamıyorsa 0.0.
        """

        if period <= 0 or duration <= 0 or len(time) < 20:
            return 0.0

        best = 0.0
        # Uc katlama da test edilir: cascade P/2 veya 2P'yi yanlis
        # secebilir. Gezegen sinyalinde 2P katlamasinda tum t_grid
        # noktalari transit'e denk gelir (hepsi ayni derinlik) -> oeh ~0.
        # EB'de P/2 veya 2P'de odd/even farki gorulur.
        for factor in (0.5, 1.0, 2.0):
            P_test = period * factor
            v = QualityMetricsCalculator._raw_odd_even_at(
                time, flux, P_test, t0, duration
            )
            if v > best:
                best = v
        return best

    @staticmethod
    def _raw_odd_even_at(
        time: np.ndarray,
        flux: np.ndarray,
        P_test: float,
        t0: float,
        duration: float,
    ) -> float:
        """Belirli bir P_test periyodunda ham veriden odd/even farkı."""

        if P_test <= 0 or duration <= 0:
            return 0.0

        n_expected = int((time.max() - time.min()) / P_test) + 1
        if n_expected < 4:
            return 0.0

        t_grid = t0 + np.arange(n_expected) * P_test
        t_grid = t_grid[
            (t_grid > time.min() + duration)
            & (t_grid < time.max() - duration)
        ]
        if len(t_grid) < 4:
            return 0.0

        # Her pozisyon icin transit dip SNR hesapla. Anlamsiz (SNR<3)
        # pozisyonlar "sahte transit" olarak atilir; boylece P/2 katlamasinda
        # yarisi gercek transit yarisi gurultu olan senaryo elenir.
        valid_dips: list[tuple[int, float]] = []
        for idx, t in enumerate(t_grid):
            m = np.abs(time - t) < duration
            o = (np.abs(time - t) > 2 * duration) & (
                np.abs(time - t) < 0.4 * P_test
            )
            if m.sum() < 3 or o.sum() < 5:
                continue
            dip, sigma = QualityMetricsCalculator._dip_amplitude(
                flux, m, o
            )
            if sigma <= 0 or dip <= 0:
                continue
            snr = dip / sigma
            if snr > 3.0:
                valid_dips.append((idx, float(dip)))

        odd_dips = [d for i, d in valid_dips if i % 2 == 0]
        even_dips = [d for i, d in valid_dips if i % 2 == 1]

        if len(odd_dips) < 2 or len(even_dips) < 2:
            return 0.0

        odd_mean = float(np.mean(odd_dips))
        even_mean = float(np.mean(even_dips))
        mean_all = 0.5 * (odd_mean + even_mean)
        if mean_all <= 0:
            return 0.0

        return float(abs(odd_mean - even_mean) / mean_all)

    @staticmethod
    def _compute_secondary_eclipse_snr(
        time: np.ndarray,
        flux: np.ndarray,
        period: float,
        t0: float,
        duration: float,
    ) -> float:
        """
        Faz 0.25 / 0.5 / 0.75'te anlamli dip SNR'ini P, P/2 ve 2P
        katlamalarinda arar; en yuksek anlamli degeri dondurur.

        Tek gezegen sinyalinde bu fazlarda anlamli dip yoktur (SNR ~ 0).
        EB ve odd-even alternatif sistemlerde karsit tutulma bu fazlardan
        birine duser ve yuksek SNR verir.

        Yanlis-pozitifi engellemek icin: secondary derinligi primary
        derinliginden kucuk olmali (ratio < 0.9). Aksi halde P/2 katlamasi
        primary'yi tekrar secondary gibi gosterir.

        Returns
        -------
        float
            En yuksek anlamli secondary SNR; hesaplanamiyorsa 0.0.
        """

        if period <= 0 or duration <= 0 or len(time) < 20:
            return 0.0

        hw = duration / 2.0
        best = 0.0

        # 2P test edilir: cascade harmonik periyot sectiginde (P_c = P_r/2),
        # 2*P_c = P_r gercek periyoda denk gelir ve secondary phase 0.5'te
        # gorulur. Gezegen sinyalinde 2P katlamasinda "secondary" bir sonraki
        # transitin kendisidir ve ratio ~ 1.0 olur; ratio < 0.9 filtresi
        # bunu eler.
        for factor in (1.0, 2.0):
            P_test = period * factor
            if P_test <= 0 or hw <= 0:
                continue
            phase = ((time - t0 + 0.5 * P_test) % P_test) - 0.5 * P_test

            # Primary (faz 0): yuksek SNR'li dip olmali; aksi halde bu
            # katlama transit icin anlamli degildir.
            dist0 = np.abs(phase)
            dist0 = np.minimum(dist0, P_test - dist0)
            m0 = dist0 < hw
            o0 = (dist0 > 2 * hw) & (dist0 < 0.25 * P_test)
            if m0.sum() < 5 or o0.sum() < 20:
                continue
            d_primary, sigma0 = QualityMetricsCalculator._dip_amplitude(
                flux, m0, o0
            )
            if sigma0 <= 0 or d_primary <= 0:
                continue
            snr_primary = d_primary / sigma0
            # Primary anlamli degilse bu katlamayi atla
            if snr_primary < 8.0:
                continue

            # Secondary: sadece phase 0.5
            target_days = 0.5 * P_test
            if target_days > 0.5 * P_test:
                target_days -= P_test
            dist = np.abs(phase - target_days)
            dist = np.minimum(dist, P_test - dist)

            in_dip = dist < hw
            out = (
                (dist > 2 * hw)
                & (dist0 > 2 * hw)
                & (dist < 0.20 * P_test)
            )
            if in_dip.sum() < 5 or out.sum() < 20:
                continue

            depth, sigma = QualityMetricsCalculator._dip_amplitude(
                flux, in_dip, out
            )
            if sigma <= 0 or depth <= 0:
                continue

            ratio = depth / d_primary
            if not (0.03 < ratio < 0.9):
                continue

            # Basit SNR: sigma kullan (korele noktalar sqrt(N)'i sisirir)
            snr = depth / sigma
            if snr > best:
                best = float(snr)

        return best

    @staticmethod
    def _dip_amplitude(
        flux: np.ndarray,
        m: np.ndarray,
        o: np.ndarray,
    ) -> tuple[float, float]:
        """Pencere icinde anlamli dip derinligi ve baseline sigma.

        Baseline'dan 2 sigma'dan fazla asagida olan noktalar 'dip' sayilir.
        Transit yoksa (0.0, sigma) doner; boylece median'in baseline'a
        kaymasi engellenir.
        """
        if m.sum() < 3 or o.sum() < 5:
            return 0.0, 0.0
        base = float(np.median(flux[o]))
        sigma = float(np.std(flux[o]))
        if sigma <= 0:
            return 0.0, 0.0
        in_dip = flux[m] < (base - 2.0 * sigma)
        if in_dip.sum() < 2:
            return 0.0, sigma
        dip_vals = flux[m][in_dip]
        depth = base - float(np.median(dip_vals))
        return float(depth), float(sigma)

    @staticmethod
    def _compute_transit_symmetry(
        phase: np.ndarray,
        flux: np.ndarray,
    ) -> float:
        """
        Faz katlanmış transit simetri skoru hesaplar.

        Yöntem:
            Transit merkezini 0.5 olarak kabul eder.
            Sol ve sağ yarıları karşılaştırır.
            Simetri = 1 - normalize(|sol - sağ|)

        Returns
        -------
        float
            Simetri skoru (0-1, 1=mükemmel simetri).
        """

        if len(phase) < 20:
            return 0.5

        # Transit merkezi etrafında ±0.1 faz penceresi
        transit_mask = np.abs(phase - 0.5) < 0.1
        in_transit = flux[transit_mask]
        in_phase = phase[transit_mask]

        if len(in_transit) < 6:
            return 0.5

        # Sol ve sağ yarılar (transit merkezine göre)
        center_phase = 0.5
        left_mask = in_phase < center_phase
        right_mask = in_phase >= center_phase

        if left_mask.sum() < 3 or right_mask.sum() < 3:
            return 0.5

        left_mean = float(np.mean(in_transit[left_mask]))
        right_mean = float(np.mean(in_transit[right_mask]))

        # Normalize asimetri
        transit_depth = 1.0 - float(np.min(in_transit))

        if transit_depth <= 0:
            return 0.5

        asymmetry = abs(left_mean - right_mean) / transit_depth
        symmetry = float(np.clip(1.0 - asymmetry, 0.0, 1.0))

        return symmetry

    @staticmethod
    def _compute_timing_rms(
        transit_times: np.ndarray,
        period: float,
    ) -> float:
        """
        Transit zamanlama residual RMS hesaplar (TTV göstergesi).

        Gözlenen transit zamanları ile lineer efemeris
        arasındaki fark.

        Returns
        -------
        float
            Timing residual RMS (gün).
        """

        if len(transit_times) < 3 or period <= 0:
            return 0.0

        t0 = transit_times[0]
        n = np.round((transit_times - t0) / period).astype(int)
        expected_times = t0 + n * period
        residuals = transit_times - expected_times

        return float(np.sqrt(np.mean(residuals ** 2)))

    @staticmethod
    def _lomb_scargle_peak(
        time: np.ndarray,
        flux: np.ndarray,
        min_period: float = 0.1,
        max_period: float = 30.0,
    ) -> tuple[float, float]:
        """
        Lomb-Scargle periodogram en güçlü periyot ve gücünü döndürür.

        Returns
        -------
        tuple[float, float]
            (periyot gün, güç).
        """

        from astropy.timeseries import LombScargle

        if len(time) < 20:
            return 0.0, 0.0

        try:
            residual = flux - 1.0
            ls = LombScargle(time, residual)

            frequency, power = ls.autopower(
                minimum_frequency=1.0 / max_period,
                maximum_frequency=1.0 / min_period,
            )

            if len(power) == 0:
                return 0.0, 0.0

            best_idx = np.argmax(power)
            best_period = float(1.0 / frequency[best_idx])
            best_power = float(power[best_idx])

            return best_period, best_power

        except Exception as e:
            logger.debug(f"Lomb-Scargle hatası: {e}")
            return 0.0, 0.0

    @staticmethod
    def _check_secondary_eclipse(
        time: np.ndarray,
        flux: np.ndarray,
        period: float,
        t0: float,
        phase_window: float = 0.05,
    ) -> float:
        """
        İkincil tutulma derinliğini tahmin eder.

        Faz 0.5'teki (karşı tutulma) derinliği ölçer.
        Yüksek değer → gezegen değil EB şüphesi.

        Returns
        -------
        float
            İkincil tutulma derinliği (göreli birim).
        """

        if period <= 0 or len(time) < 20:
            return 0.0

        try:
            # Faz hesapla
            phase = ((time - t0) % period) / period

            # Faz 0.5 etrafında
            secondary_mask = np.abs(phase - 0.5) < phase_window

            if secondary_mask.sum() < 5:
                return 0.0

            secondary_flux = flux[secondary_mask]
            # Baseline: primary transit ve secondary dışındaki bölgeler
            primary_mask = np.abs(phase) < phase_window
            oot_mask = (~secondary_mask) & (~primary_mask)

            if oot_mask.sum() < 5:
                return 0.0

            sec_sorted = np.sort(secondary_flux)
            n_deep_sec = max(3, int(0.25 * len(sec_sorted)))
            secondary_median = float(np.median(sec_sorted[:n_deep_sec]))
            oot_median = float(np.median(flux[oot_mask]))

            depth = oot_median - secondary_median
            return max(0.0, float(depth))

        except Exception:
            return 0.0
