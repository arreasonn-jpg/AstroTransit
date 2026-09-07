"""
İleri temizleme modülü.

Normalizasyon sonrası ek kalite kontrolleri ve veri temizleme.
Veri boşluklarını tespit eder, sürekli segmentlere böler
ve edge artifact'larını giderir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from loguru import logger

from astrotransit.preprocessing.normalization import NormalizedLightCurve


# ──────────────────────────────────────
# Segment veri modeli
# ──────────────────────────────────────
@dataclass
class LightCurveSegment:
    """
    Sürekli bir veri segmenti.

    Büyük boşluklarla bölünmüş bir light curve içinde
    her kesintisiz bloku temsil eder.

    Attributes
    ----------
    time : np.ndarray
        Segment zaman dizisi.
    flux : np.ndarray
        Segment flux dizisi.
    flux_err : np.ndarray
        Segment hata dizisi.
    start_time : float
        Segment başlangıç zamanı.
    end_time : float
        Segment bitiş zamanı.
    segment_index : int
        Segment sıra numarası.
    """

    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    start_time: float
    end_time: float
    segment_index: int

    @property
    def duration_days(self) -> float:
        """Segment süresi (gün)."""
        return self.end_time - self.start_time

    @property
    def n_points(self) -> int:
        """Nokta sayısı."""
        return len(self.time)


@dataclass
class CleanedLightCurve:
    """
    İleri temizleme uygulanmış light curve.

    Attributes
    ----------
    target_id : str
        Hedef TIC ID.
    sector : int
        Sektör numarası.
    time : np.ndarray
        Temizlenmiş zaman dizisi.
    flux : np.ndarray
        Temizlenmiş normalize flux dizisi.
    flux_err : np.ndarray
        Temizlenmiş hata dizisi.
    segments : list[LightCurveSegment]
        Sürekli veri segmentleri.
    n_points_input : int
        Temizleme öncesi nokta sayısı.
    n_gaps_detected : int
        Tespit edilen boşluk sayısı.
    meta : dict
        Ek metadata.
    """

    target_id: str
    sector: int
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    segments: list[LightCurveSegment]
    n_points_input: int
    n_gaps_detected: int
    meta: dict = field(default_factory=dict)

    @property
    def n_points(self) -> int:
        return len(self.time)

    @property
    def n_segments(self) -> int:
        return len(self.segments)

    @property
    def completeness(self) -> float:
        if self.n_points_input == 0:
            return 0.0
        return self.n_points / self.n_points_input

    def summary(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "n_points_input": self.n_points_input,
            "n_points_output": self.n_points,
            "n_segments": self.n_segments,
            "n_gaps": self.n_gaps_detected,
            "completeness": round(self.completeness, 4),
        }


# ──────────────────────────────────────
# Temizleyici sınıf
# ──────────────────────────────────────
class LightCurveCleaner:
    """
    İleri light curve temizleyici.

    Normalizasyon sonrası ek kalite kontrolü ve veri
    segmentasyonu uygular.

    Parameters
    ----------
    gap_threshold_days : float
        Bu süreden uzun boşluklar segment sınırı sayılır.
    sigma_clip_flux : float
        Flux sigma kırpma eşiği (normalize flux için).
    min_segment_points : int
        Geçerli segment için minimum nokta sayısı.
    clip_edge_points : int
        Her segmentin başından ve sonundan kesilecek
        edge nokta sayısı.
    """

    def __init__(
        self,
        gap_threshold_days: float = 0.5,
        sigma_clip_flux: float = 5.0,
        min_segment_points: int = 50,
        clip_edge_points: int = 3,
    ):
        self.gap_threshold_days = gap_threshold_days
        self.sigma_clip_flux = sigma_clip_flux
        self.min_segment_points = min_segment_points
        self.clip_edge_points = clip_edge_points

        logger.debug(
            f"LightCurveCleaner — "
            f"gap_threshold: {gap_threshold_days}d, "
            f"sigma: {sigma_clip_flux}, "
            f"min_segment: {min_segment_points}"
        )

    def _detect_gaps(self, time: np.ndarray) -> list[int]:
        """
        Zaman dizisinde büyük boşlukları tespit eder.

        Parameters
        ----------
        time : np.ndarray
            Sıralı zaman dizisi.

        Returns
        -------
        list[int]
            Boşluk noktalarının indeksleri (boşluktan sonraki nokta).
        """

        if len(time) < 2:
            return []

        dt = np.diff(time)
        gap_indices = np.where(dt > self.gap_threshold_days)[0] + 1

        return gap_indices.tolist()

    def _split_segments(
        self,
        time: np.ndarray,
        flux: np.ndarray,
        flux_err: np.ndarray,
    ) -> list[LightCurveSegment]:
        """
        Light curve'ü sürekli segmentlere böler.

        Parameters
        ----------
        time, flux, flux_err : np.ndarray
            Zaman, flux ve hata dizileri.

        Returns
        -------
        list[LightCurveSegment]
            Tespit edilen segmentler.
        """

        gap_indices = self._detect_gaps(time)

        # Tüm bölünme noktaları
        split_points = [0] + gap_indices + [len(time)]

        segments = []

        for i, (start, end) in enumerate(zip(split_points[:-1], split_points[1:])):
            seg_time = time[start:end]
            seg_flux = flux[start:end]
            seg_err = flux_err[start:end]

            # Edge temizleme
            if self.clip_edge_points > 0 and len(seg_time) > 2 * self.clip_edge_points + 10:
                seg_time = seg_time[self.clip_edge_points:-self.clip_edge_points]
                seg_flux = seg_flux[self.clip_edge_points:-self.clip_edge_points]
                seg_err = seg_err[self.clip_edge_points:-self.clip_edge_points]

            # Minimum nokta kontrolü
            if len(seg_time) < self.min_segment_points:
                logger.debug(
                    f"Segment {i} atlandı: "
                    f"{len(seg_time)} nokta < minimum {self.min_segment_points}"
                )
                continue

            segment = LightCurveSegment(
                time=seg_time,
                flux=seg_flux,
                flux_err=seg_err,
                start_time=float(seg_time[0]),
                end_time=float(seg_time[-1]),
                segment_index=i,
            )
            segments.append(segment)

        return segments

    def _sigma_clip_flux(
        self,
        flux: np.ndarray,
    ) -> np.ndarray:
        """
        Normalize flux üzerinde sigma kırpma maskesi üretir.

        Normalize flux için merkez değer 1.0 civarı olduğundan
        medyan etrafında sigma hesaplanır.

        Parameters
        ----------
        flux : np.ndarray
            Normalize flux dizisi.

        Returns
        -------
        np.ndarray
            Boolean maske (True = geçerli).
        """

        median = np.nanmedian(flux)
        std = np.nanstd(flux)

        if std == 0:
            return np.ones(len(flux), dtype=bool)

        mask = np.abs(flux - median) < self.sigma_clip_flux * std
        return mask

    def clean(self, normalized: NormalizedLightCurve) -> CleanedLightCurve:
        """
        Normalize edilmiş light curve üzerinde ileri temizleme uygular.

        Adımlar:
            1. Sigma kırpma (aykırı flux noktaları)
            2. Boşluk tespiti
            3. Segmentlere bölme
            4. Edge artifact temizliği
            5. Minimum segment filtresi

        Parameters
        ----------
        normalized : NormalizedLightCurve
            Normalize edilmiş light curve.

        Returns
        -------
        CleanedLightCurve
            Temizlenmiş ve segmentlenmiş light curve.
        """

        n_input = normalized.n_points

        logger.info(
            f"İleri temizleme başlıyor — "
            f"{normalized.target_id} sektör {normalized.sector}: "
            f"{n_input} nokta"
        )

        time = normalized.time.copy()
        flux = normalized.flux.copy()
        flux_err = normalized.flux_err.copy()

        # ── Adım 1: Sigma kırpma ──
        sigma_mask = self._sigma_clip_flux(flux)
        n_clipped = (~sigma_mask).sum()

        if n_clipped > 0:
            logger.debug(f"Sigma kırpma: {n_clipped} nokta çıkarıldı")

        time = time[sigma_mask]
        flux = flux[sigma_mask]
        flux_err = flux_err[sigma_mask]

        # ── Adım 2-4: Segmentlere bölme ──
        n_gaps = len(self._detect_gaps(time))

        segments = self._split_segments(time, flux, flux_err)

        if not segments:
            raise ValueError(
                f"{normalized.target_id} sektör {normalized.sector}: "
                f"temizleme sonrası geçerli segment kalmadı."
            )

        # ── Tüm segmentleri birleştir ──
        all_time = np.concatenate([s.time for s in segments])
        all_flux = np.concatenate([s.flux for s in segments])
        all_err = np.concatenate([s.flux_err for s in segments])

        # Zaman sırasına göre sırala
        sort_idx = np.argsort(all_time)
        all_time = all_time[sort_idx]
        all_flux = all_flux[sort_idx]
        all_err = all_err[sort_idx]

        result = CleanedLightCurve(
            target_id=normalized.target_id,
            sector=normalized.sector,
            time=all_time,
            flux=all_flux,
            flux_err=all_err,
            segments=segments,
            n_points_input=n_input,
            n_gaps_detected=n_gaps,
            meta=normalized.meta.copy(),
        )

        logger.info(
            f"Temizleme tamamlandı — "
            f"girdi: {n_input}, "
            f"çıktı: {result.n_points}, "
            f"segment: {result.n_segments}, "
            f"boşluk: {n_gaps}"
        )

        return result