"""
Kademeli transit tespit sistemi (BLS → TLS).

Karar akışı:
    1. BLS hızlı tarama
       ↓ aday yok → CascadeCandidate(status=BLS_FAILED)
       ↓ aday var
    2. TLS doğrulama
       ↓ başarısız → CascadeCandidate(status=TLS_FAILED)
       ↓ başarılı
    3. Periyot uyum kontrolü
       ↓ uyumsuz → CascadeCandidate(status=PERIOD_MISMATCH)
       ↓ uyumlu
    4. CascadeCandidate(status=CONFIRMED) → Modelleme aşamasına geç
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.preprocessing.tess_detrend import DetrendedLightCurve
from astrotransit.detection.thresholds import CascadeThresholds
from astrotransit.detection.bls_search import BLSSearch, BLSResult, BLSPeak
from astrotransit.detection.tls_search import TLSSearch, TLSResult
from astrotransit.settings import Settings, get_settings


# ──────────────────────────────────────
# Durum enumları
# ──────────────────────────────────────
class CascadeStatus(str, Enum):
    """Kademeli tespit sistemi karar durumları."""

    CONFIRMED = "confirmed"
    BLS_ONLY = "bls_only"
    BLS_FAILED = "bls_failed"
    TLS_FAILED = "tls_failed"
    PERIOD_MISMATCH = "period_mismatch"
    ERROR = "error"


# ──────────────────────────────────────
# Sonuç veri modeli
# ──────────────────────────────────────
@dataclass
class CascadeCandidate:
    """Kademeli tespit sisteminin nihai çıktısı."""

    target_id: str
    sector: int
    status: CascadeStatus
    confirmed: bool
    bls_result: BLSResult
    tls_result: Optional[TLSResult]

    # Nihai kabul edilen parametreler
    period: float = 0.0
    period_err: float = 0.0
    t0: float = 0.0
    duration: float = 0.0
    depth: float = 0.0
    rp_rs: float = 0.0
    snr: float = 0.0
    sde: float = 0.0
    transit_times: np.ndarray = field(default_factory=lambda: np.array([]))
    decision_log: list[str] = field(default_factory=list)

    @property
    def has_candidate(self) -> bool:
        """
        En azından bir aday sinyal tespit edildi mi?

        BLS bir tepe bulduysa (durum ne olursa olsun) True döner.
        Sadece BLS_FAILED durumunda False'tur.
        """
        return self.status != CascadeStatus.BLS_FAILED

    def to_dict(self) -> dict:
        """Serileştirilebilir sözlük."""
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "status": self.status.value,
            "confirmed": self.confirmed,
            "has_candidate": self.has_candidate,
            "period": round(self.period, 6),
            "period_err": round(self.period_err, 6),
            "t0": round(self.t0, 6),
            "duration_hours": round(self.duration * 24, 4),
            "depth_ppm": round(self.depth * 1e6, 2),
            "rp_rs": round(self.rp_rs, 6),
            "snr": round(self.snr, 4),
            "sde": round(self.sde, 4),
            "n_transits": len(self.transit_times),
            "decision_log": self.decision_log,
        }

    def summary(self) -> dict:
        return self.to_dict()


# ──────────────────────────────────────
# Kademeli tespit motoru
# ──────────────────────────────────────
class CascadeDetector:
    """
    BLS → TLS kademeli transit tespit motoru.

    Parameters
    ----------
    settings : Settings, opsiyonel
        Proje konfigürasyonu.
    thresholds : CascadeThresholds, opsiyonel
        Cascade eşik değerleri.
    stellar_radius : float
        Yıldız yarıçapı (R_sun). TLS için kullanılır.
    stellar_mass : float
        Yıldız kütlesi (M_sun). TLS için kullanılır.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        thresholds: Optional[CascadeThresholds] = None,
        stellar_radius: float = 1.0,
        stellar_mass: float = 1.0,
    ):
        if settings is None:
            settings = get_settings()

        self.settings = settings

        if thresholds is None:
            thresholds = CascadeThresholds.from_settings(settings)

        self.thresholds = thresholds
        self.stellar_radius = stellar_radius
        self.stellar_mass = stellar_mass

        # Alt motorlar
        self._bls = BLSSearch(
            thresholds=thresholds.bls,
            n_durations=settings.detection.bls.n_durations,
            frequency_factor=settings.detection.frequency_factor,
        )

        self._tls = TLSSearch(
            thresholds=thresholds.tls,
            oversampling_factor=settings.detection.tls.oversampling_factor,
            use_stellar_params=True,
            transit_template=(
                "default"
                if settings.detection.tls.use_transit_template
                else "box"
            ),
            period_search_window=settings.detection.tls.period_search_window,
        )

        logger.info(
            f"CascadeDetector başlatıldı — "
            f"require_both: {thresholds.require_both}, "
            f"period_tol: {thresholds.period_tolerance}, "
            f"R*: {stellar_radius:.2f} Rsun, "
            f"M*: {stellar_mass:.2f} Msun"
        )

    def _check_period_agreement(
        self,
        bls_period: float,
        tls_period: float,
    ) -> tuple[bool, float]:
        """BLS ve TLS periyotlarının uyumunu kontrol eder."""

        if bls_period <= 0 or tls_period <= 0:
            return False, 999.0

        # Genişletilmiş harmonik kontrolü
        # BLS bazen 1/3, 1/2, 2x, 3x harmonikler bulur
        harmonic_factors = [1/3, 1/2, 1.0, 2.0, 3.0]

        best_rel_diff = float('inf')
        best_factor = 1.0

        for factor in harmonic_factors:
            harmonic_period = bls_period * factor
            if harmonic_period > 0:
                rel = abs(harmonic_period - tls_period) / harmonic_period
                if rel < best_rel_diff:
                    best_rel_diff = rel
                    best_factor = factor

        if best_rel_diff < self.thresholds.period_tolerance:
            if best_factor != 1.0:
                logger.info(
                    f"Harmonik eşleşme: BLS P={bls_period:.4f}d × {best_factor:.3f} "
                    f"≈ TLS P={tls_period:.4f}d (rel_diff={best_rel_diff:.4f})"
                )
            return True, best_rel_diff

        return False, best_rel_diff

    def detect(
        self,
        detrended: DetrendedLightCurve,
    ) -> CascadeCandidate:
        """
        Kademeli transit tespitini çalıştırır.

        Parameters
        ----------
        detrended : DetrendedLightCurve
            Detrend edilmiş light curve.

        Returns
        -------
        CascadeCandidate
            Tespit sonucu ve nihai parametreler.
        """

        target_id = detrended.target_id
        sector = detrended.sector
        log = []

        logger.info(
            f"Cascade tespiti — {target_id} sektör {sector}"
        )

        # ═══════════════════════════════
        # ADIM 1: BLS Tarama
        # ═══════════════════════════════
        try:
            bls_result = self._bls.search(detrended)
        except Exception as e:
            logger.error(f"BLS taraması hatası: {e}")
            log.append(f"BLS hata: {e}")
            return CascadeCandidate(
                target_id=target_id,
                sector=sector,
                status=CascadeStatus.ERROR,
                confirmed=False,
                bls_result=BLSResult(
                    target_id=target_id,
                    sector=sector,
                    best=None,
                    all_peaks=[],
                    periods_searched=np.array([]),
                    power_array=np.array([]),
                    n_periods_searched=0,
                    has_candidate=False,
                ),
                tls_result=None,
                decision_log=log,
            )

        log.append(
            f"BLS: n_period={bls_result.n_periods_searched}, "
            f"has_candidate={bls_result.has_candidate}"
        )

        if not bls_result.has_candidate:
            log.append("BLS eşiği geçilemedi → sonlandı.")
            logger.info(f"{target_id} sektör {sector}: BLS aday yok.")

            return CascadeCandidate(
                target_id=target_id,
                sector=sector,
                status=CascadeStatus.BLS_FAILED,
                confirmed=False,
                bls_result=bls_result,
                tls_result=None,
                decision_log=log,
            )

        bls_peak: BLSPeak = bls_result.best

        log.append(
            f"BLS aday: P={bls_peak.period:.4f}d, "
            f"derinlik={bls_peak.depth * 1e6:.0f}ppm, "
            f"güç={bls_peak.power:.2f}"
        )

        # ═══════════════════════════════
        # ADIM 2: TLS Doğrulama (en iyi N adayı sırayla dene)
        # ═══════════════════════════════

        # BLS'nin en iyi N adayını al (en güçlüden zayıfa sıralı)
        passed_peaks = [p for p in bls_result.all_peaks if p.passed_threshold]

        if not passed_peaks:
            passed_peaks = [bls_result.best]

        # En fazla 3 aday dene
        candidates_to_try = passed_peaks[:1]  # hizli tarama modu: sadece en iyi BLS adayi

        log.append(
            f"BLS: {len(candidates_to_try)} aday TLS ile denenecek (hizli mod)"
        )

        best_tls_result = None
        best_bls_peak = None
        best_score = -1.0  # SDE * SNR ile skor

        for idx, bls_peak_try in enumerate(candidates_to_try):
            log.append(
                f"  Aday {idx + 1}: P={bls_peak_try.period:.4f}d, "
                f"güç={bls_peak_try.power:.2f}"
            )

            try:
                tls_try = self._tls.validate(
                    detrended,
                    bls_peak_try,
                    stellar_radius=self.stellar_radius,
                    stellar_mass=self.stellar_mass,
                )
            except Exception as e:
                logger.debug(f"TLS aday {idx + 1} hatası: {e}")
                continue

            # Bu adayın kalite skoru: SDE * SNR
            if tls_try.passed_threshold:
                score = tls_try.sde * np.sqrt(max(1.0, tls_try.snr))

                # Periyot BLS ile uyumlu mu?
                period_ok, _ = self._check_period_agreement(
                    bls_peak_try.period, tls_try.period
                )

                if period_ok and score > best_score:
                    best_score = score
                    best_tls_result = tls_try
                    best_bls_peak = bls_peak_try
                    log.append(
                        f"  → Aday {idx + 1} EN İYİ: "
                        f"SDE={tls_try.sde:.2f}, SNR={tls_try.snr:.2f}"
                    )

        # Hiç aday başarılı olmadıysa en güçlü BLS adayının TLS sonucunu al
        if best_tls_result is None:
            best_bls_peak = candidates_to_try[0]
            try:
                best_tls_result = self._tls.validate(
                    detrended,
                    best_bls_peak,
                    stellar_radius=self.stellar_radius,
                    stellar_mass=self.stellar_mass,
                )
            except Exception as e:
                logger.error(f"TLS doğrulama hatası: {e}")
                log.append(f"TLS hata: {e}")

                if not self.thresholds.require_both:
                    log.append("require_both=False → BLS adayı kabul edildi (TLS hatası).")
                    return self._build_bls_only_candidate(
                        target_id, sector, bls_result, None, best_bls_peak, log
                    )
                else:
                    return CascadeCandidate(
                        target_id=target_id,
                        sector=sector,
                        status=CascadeStatus.TLS_FAILED,
                        confirmed=False,
                        bls_result=bls_result,
                        tls_result=None,
                        period=best_bls_peak.period,
                        period_err=best_bls_peak.period_err,
                        t0=best_bls_peak.t0,
                        duration=best_bls_peak.duration,
                        depth=best_bls_peak.depth,
                        rp_rs=float(np.sqrt(max(0.0, best_bls_peak.depth))),
                        snr=best_bls_peak.snr,
                        sde=0.0,
                        transit_times=best_bls_peak.transit_times,
                        decision_log=log,
                    )

        # Bundan sonra bls_peak ve tls_result değişkenlerini kullan
        bls_peak = best_bls_peak
        tls_result = best_tls_result

        log.append(
            f"TLS: SDE={tls_result.sde:.2f}, "
            f"SNR={tls_result.snr:.2f}, "
            f"P={tls_result.period:.4f}d, "
            f"passed={tls_result.passed_threshold}"
        )

        # ═══════════════════════════════
        # ADIM 3: Periyot Uyum Kontrolü
        # ═══════════════════════════════
        period_ok, rel_diff = self._check_period_agreement(
            bls_peak.period,
            tls_result.period,
        )

        log.append(
            f"Periyot uyumu: BLS={bls_peak.period:.4f}d, "
            f"TLS={tls_result.period:.4f}d, "
            f"rel_diff={rel_diff:.4f}, "
            f"uyumlu={period_ok}"
        )

        if not period_ok:
            log.append(
                f"Periyot uyumsuz "
                f"(rel_diff={rel_diff:.4f} > tol={self.thresholds.period_tolerance})"
            )

            return CascadeCandidate(
                target_id=target_id,
                sector=sector,
                status=CascadeStatus.PERIOD_MISMATCH,
                confirmed=False,
                bls_result=bls_result,
                tls_result=tls_result,
                period=tls_result.period,
                period_err=tls_result.period_err,
                t0=tls_result.t0,
                duration=tls_result.duration,
                depth=tls_result.depth,
                rp_rs=tls_result.rp_rs,
                snr=tls_result.snr,
                sde=tls_result.sde,
                transit_times=tls_result.transit_times,
                decision_log=log,
            )

        # ═══════════════════════════════
        # ADIM 4: Aday Onayı
        # ═══════════════════════════════
        log.append("Cascade onaylandı → modelleme aşamasına geçiliyor.")

        candidate = CascadeCandidate(
            target_id=target_id,
            sector=sector,
            status=CascadeStatus.CONFIRMED,
            confirmed=True,
            bls_result=bls_result,
            tls_result=tls_result,
            period=tls_result.period,
            period_err=tls_result.period_err,
            t0=tls_result.t0,
            duration=tls_result.duration,
            depth=tls_result.depth,
            rp_rs=tls_result.rp_rs,
            snr=tls_result.snr,
            sde=tls_result.sde,
            transit_times=tls_result.transit_times,
            decision_log=log,
        )

        logger.info(
            f"Transit adayı ONAYLANDI — "
            f"{target_id} sektör {sector}: "
            f"P={candidate.period:.4f}d, "
            f"Rp/Rs={candidate.rp_rs:.4f}, "
            f"SDE={candidate.sde:.2f}, "
            f"SNR={candidate.snr:.2f}"
        )

        return candidate

    def _build_bls_only_candidate(
        self,
        target_id: str,
        sector: int,
        bls_result: BLSResult,
        tls_result: Optional[TLSResult],
        bls_peak: BLSPeak,
        log: list[str],
    ) -> CascadeCandidate:
        """BLS-only aday oluşturur (require_both=False durumu)."""

        sde_val = tls_result.sde if tls_result is not None else 0.0

        return CascadeCandidate(
            target_id=target_id,
            sector=sector,
            status=CascadeStatus.BLS_ONLY,
            confirmed=False,
            bls_result=bls_result,
            tls_result=tls_result,
            period=bls_peak.period,
            period_err=bls_peak.period_err,
            t0=bls_peak.t0,
            duration=bls_peak.duration,
            depth=bls_peak.depth,
            rp_rs=float(np.sqrt(max(0.0, bls_peak.depth))),
            snr=bls_peak.snr,
            sde=sde_val,
            transit_times=bls_peak.transit_times,
            decision_log=log,
        )

    def detect_multi_sector(
        self,
        sectors: list[DetrendedLightCurve],
    ) -> list[CascadeCandidate]:
        """Birden fazla sektör üzerinde cascade tespiti çalıştırır."""

        if not sectors:
            return []

        target_id = sectors[0].target_id

        logger.info(
            f"Çok sektör cascade — {target_id}: {len(sectors)} sektör"
        )

        results = []

        for detrended in sectors:
            try:
                candidate = self.detect(detrended)
                results.append(candidate)
            except Exception as e:
                logger.error(f"Sektör {detrended.sector} cascade hatası: {e}")
                continue

        confirmed = sum(1 for r in results if r.confirmed)
        logger.info(
            f"Çok sektör cascade tamamlandı — "
            f"{target_id}: {confirmed}/{len(results)} sektörde aday onaylandı"
        )

        return results

    def get_best_candidate(
        self,
        candidates: list[CascadeCandidate],
    ) -> Optional[CascadeCandidate]:
        """Birden fazla sektör sonucundan en güçlü adayı seçer."""

        if not candidates:
            return None

        confirmed = [c for c in candidates if c.confirmed]

        if confirmed:
            return max(confirmed, key=lambda c: c.snr)

        return max(candidates, key=lambda c: c.sde)