# astrotransit/quality/transit_consistency.py
"""
Stacked / phase-folded transit tutarlılık analiz modülü.

Amaç
----
Bir adayın transit sinyalinin transitten transite ve şekil bazında
ne kadar tutarlı olduğunu ölçmek.

Uygulanan testler
-----------------
1. Even/Odd depth consistency      — EB şüphesi
2. Transit-to-transit repeatability — derinlik kararlılığı
3. V-shape metric                  — grazing EB / planet ayrımı
4. Ingress/Egress symmetry         — şekil asimetrisi

Çıktı
-----
TransitConsistencyReport
    flag: "CONSISTENT" | "VARIABLE" | "EB_SUSPECT"
    score: 0.0 → 1.0 arası anomaly skoru
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from astrotransit.quality.vetting import VettingVerdict


# ──────────────────────────────────────────────────────────────
# Eşikler
# ──────────────────────────────────────────────────────────────

_MIN_INTRANSIT_POINTS = 7
_MIN_TRANSITS_FOR_EVEN_ODD = 4
_MIN_TRANSITS_FOR_REPEATABILITY = 3

# Even/Odd fractional mismatch
_EVEN_ODD_WARN = 0.15
_EVEN_ODD_FAIL = 0.30

# Transit-to-transit normalized scatter
_REPEAT_WARN = 0.25
_REPEAT_FAIL = 0.40

# V-shape score = wing_depth / center_depth
# 1.0'a yakınsa V-shape; düşükse daha U-shape
_VSHAPE_WARN = 0.65
_VSHAPE_FAIL = 0.85

# Ingress/egress half-depth extent asymmetry
_ASYM_WARN = 0.20
_ASYM_FAIL = 0.40


# ──────────────────────────────────────────────────────────────
# Tek test sonucu
# ──────────────────────────────────────────────────────────────

@dataclass
class TransitConsistencyTest:
    """Tek bir transit consistency testi sonucu."""

    name: str
    verdict: VettingVerdict
    value: float
    warn_threshold: float
    fail_threshold: float
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict.value,
            "value": round(float(self.value), 6),
            "warn_threshold": round(float(self.warn_threshold), 6),
            "fail_threshold": round(float(self.fail_threshold), 6),
            "description": self.description,
        }


# ──────────────────────────────────────────────────────────────
# Rapor
# ──────────────────────────────────────────────────────────────

@dataclass
class TransitConsistencyReport:
    """
    Transit consistency analiz raporu.
    """

    target_id: str
    sector: int
    n_intransit: int = 0
    n_transits: int = 0
    tests: list[TransitConsistencyTest] = field(default_factory=list)
    flag: str = "UNKNOWN"
    score: float = 0.0
    n_pass: int = 0
    n_warn: int = 0
    n_fail: int = 0
    n_skip: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "n_intransit": self.n_intransit,
            "n_transits": self.n_transits,
            "flag": self.flag,
            "score": round(float(self.score), 4),
            "n_pass": self.n_pass,
            "n_warn": self.n_warn,
            "n_fail": self.n_fail,
            "n_skip": self.n_skip,
            "details": {
                k: round(float(v), 6) if isinstance(v, float) else v
                for k, v in self.details.items()
            },
            "tests": [t.to_dict() for t in self.tests],
        }

    def summary(self) -> str:
        return (
            f"{self.target_id} S{self.sector} | "
            f"flag={self.flag} score={self.score:.3f} | "
            f"pass={self.n_pass} warn={self.n_warn} "
            f"fail={self.n_fail} skip={self.n_skip} | "
            f"n_transits={self.n_transits}"
        )


# ──────────────────────────────────────────────────────────────
# Analizör
# ──────────────────────────────────────────────────────────────

class TransitConsistencyAnalyzer:
    """
    Phase-folded / stacked transit tutarlılık analizörü.

    Parametreler
    ------------
    even_odd_warn, even_odd_fail
        Even/odd fractional depth mismatch eşikleri.
    repeat_warn, repeat_fail
        Transit-to-transit normalized scatter eşikleri.
    vshape_warn, vshape_fail
        Wing/center depth ratio eşikleri.
    asym_warn, asym_fail
        Ingress/egress half-depth extent asymmetry eşikleri.
    """

    def __init__(
        self,
        even_odd_warn: float = _EVEN_ODD_WARN,
        even_odd_fail: float = _EVEN_ODD_FAIL,
        repeat_warn: float = _REPEAT_WARN,
        repeat_fail: float = _REPEAT_FAIL,
        vshape_warn: float = _VSHAPE_WARN,
        vshape_fail: float = _VSHAPE_FAIL,
        asym_warn: float = _ASYM_WARN,
        asym_fail: float = _ASYM_FAIL,
    ):
        self.even_odd_warn = even_odd_warn
        self.even_odd_fail = even_odd_fail
        self.repeat_warn = repeat_warn
        self.repeat_fail = repeat_fail
        self.vshape_warn = vshape_warn
        self.vshape_fail = vshape_fail
        self.asym_warn = asym_warn
        self.asym_fail = asym_fail

        logger.debug("TransitConsistencyAnalyzer başlatıldı.")

    def analyze(
        self,
        target_id: str,
        sector: int,
        phase: np.ndarray,
        flux: np.ndarray,
        in_transit_mask: np.ndarray,
        transit_event_ids: Optional[np.ndarray] = None,
        per_transit_depths: Optional[np.ndarray] = None,
    ) -> TransitConsistencyReport:
        """
        Transit consistency analizini çalıştırır.

        Parameters
        ----------
        target_id : str
            TIC ID.
        sector : int
            Sektör numarası.
        phase : np.ndarray
            Phase-folded zaman/evre dizisi. Mid-transit ~ 0 olmalı.
        flux : np.ndarray
            Detrended, normalize flux.
        in_transit_mask : np.ndarray
            Transit içi maske.
        transit_event_ids : np.ndarray, optional
            Her noktanın ait olduğu transit event ID'si.
            Transit-to-transit depth tahmini için kullanılır.
        per_transit_depths : np.ndarray, optional
            Önceden hesaplanmış bireysel transit derinlikleri.

        Returns
        -------
        TransitConsistencyReport
        """

        logger.info(f"Transit consistency analizi başlıyor — {target_id} S{sector}")

        valid = (
            np.isfinite(phase)
            & np.isfinite(flux)
            & np.isfinite(in_transit_mask.astype(float))
        )

        phase_clean = np.asarray(phase)[valid]
        flux_clean = np.asarray(flux)[valid]
        mask_clean = np.asarray(in_transit_mask)[valid].astype(bool)

        event_ids_clean = None
        if transit_event_ids is not None:
            transit_event_ids = np.asarray(transit_event_ids)
            if len(transit_event_ids) == len(phase):
                event_ids_clean = transit_event_ids[valid]
            else:
                logger.warning("transit_event_ids uzunluğu phase ile eşleşmiyor; yok sayılıyor.")

        in_phase = phase_clean[mask_clean]
        in_flux = flux_clean[mask_clean]
        n_in = len(in_phase)

        baseline = self._estimate_baseline(flux_clean, mask_clean)
        per_depths = self._resolve_per_transit_depths(
            flux=flux_clean,
            in_transit_mask=mask_clean,
            transit_event_ids=event_ids_clean,
            per_transit_depths=per_transit_depths,
            baseline=baseline,
        )

        tests: list[TransitConsistencyTest] = []

        tests.append(self._test_even_odd_depth_consistency(per_depths))
        tests.append(self._test_transit_repeatability(per_depths))
        tests.append(self._test_v_shape_metric(in_phase, in_flux, baseline))
        tests.append(self._test_ingress_egress_symmetry(in_phase, in_flux, baseline))

        n_pass = sum(1 for t in tests if t.verdict == VettingVerdict.PASS)
        n_warn = sum(1 for t in tests if t.verdict == VettingVerdict.WARN)
        n_fail = sum(1 for t in tests if t.verdict == VettingVerdict.FAIL)
        n_skip = sum(1 for t in tests if t.verdict == VettingVerdict.SKIP)

        details = self._compute_details(
            phase_in=in_phase,
            flux_in=in_flux,
            baseline=baseline,
            per_depths=per_depths,
        )

        score = self._compute_score(tests)
        flag = self._compute_flag(tests, score, n_fail, n_warn)

        report = TransitConsistencyReport(
            target_id=target_id,
            sector=sector,
            n_intransit=n_in,
            n_transits=len(per_depths),
            tests=tests,
            flag=flag,
            score=score,
            n_pass=n_pass,
            n_warn=n_warn,
            n_fail=n_fail,
            n_skip=n_skip,
            details=details,
        )

        logger.info(f"Transit consistency tamamlandı — {report.summary()}")
        return report

    # ──────────────────────────────────────
    # Bireysel testler
    # ──────────────────────────────────────

    def _test_even_odd_depth_consistency(
        self,
        per_depths: np.ndarray,
    ) -> TransitConsistencyTest:
        """
        Even/odd transit derinlik farkı.

        metric = |median(odd) - median(even)| / median(all_depths)
        """

        name = "even_odd_depth_consistency"

        if len(per_depths) < _MIN_TRANSITS_FOR_EVEN_ODD:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.even_odd_warn,
                fail_threshold=self.even_odd_fail,
                description="Even/odd testi için yetersiz transit sayısı.",
            )

        odd = per_depths[::2]
        even = per_depths[1::2]

        if len(odd) == 0 or len(even) == 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.even_odd_warn,
                fail_threshold=self.even_odd_fail,
                description="Odd/even grupları oluşturulamadı.",
            )

        med_all = float(np.median(per_depths))
        if med_all <= 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.even_odd_warn,
                fail_threshold=self.even_odd_fail,
                description="Geçersiz median transit derinliği.",
            )

        med_odd = float(np.median(odd))
        med_even = float(np.median(even))
        frac_diff = abs(med_odd - med_even) / med_all

        if frac_diff > self.even_odd_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Even/odd derinlik farkı yüksek: "
                f"{frac_diff:.3f} > {self.even_odd_fail:.3f} (EB şüphesi)"
            )
        elif frac_diff > self.even_odd_warn:
            verdict = VettingVerdict.WARN
            desc = f"Even/odd derinlik farkı uyarısı: {frac_diff:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Even/odd derinlikler tutarlı: {frac_diff:.3f}"

        return TransitConsistencyTest(
            name=name,
            verdict=verdict,
            value=float(frac_diff),
            warn_threshold=self.even_odd_warn,
            fail_threshold=self.even_odd_fail,
            description=desc,
        )

    def _test_transit_repeatability(
        self,
        per_depths: np.ndarray,
    ) -> TransitConsistencyTest:
        """
        Transit-to-transit derinlik kararlılığı.

        Robust normalized scatter:
            sigma_robust / median_depth
        """

        name = "transit_repeatability"

        if len(per_depths) < _MIN_TRANSITS_FOR_REPEATABILITY:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.repeat_warn,
                fail_threshold=self.repeat_fail,
                description="Repeatability testi için yetersiz transit sayısı (<3).",
            )

        med = float(np.median(per_depths))
        if med <= 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.repeat_warn,
                fail_threshold=self.repeat_fail,
                description="Geçersiz median transit derinliği.",
            )

        mad = float(np.median(np.abs(per_depths - med)))
        robust_sigma = 1.4826 * mad
        norm_scatter = robust_sigma / med

        if norm_scatter > self.repeat_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Transit derinlikleri kararsız: "
                f"norm_scatter={norm_scatter:.3f} > {self.repeat_fail:.3f}"
            )
        elif norm_scatter > self.repeat_warn:
            verdict = VettingVerdict.WARN
            desc = f"Transit derinlik kararlılığı uyarısı: {norm_scatter:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Transit derinlikleri tutarlı: {norm_scatter:.3f}"

        return TransitConsistencyTest(
            name=name,
            verdict=verdict,
            value=float(norm_scatter),
            warn_threshold=self.repeat_warn,
            fail_threshold=self.repeat_fail,
            description=desc,
        )

    def _test_v_shape_metric(
        self,
        in_phase: np.ndarray,
        in_flux: np.ndarray,
        baseline: float,
    ) -> TransitConsistencyTest:
        """
        V-shape metriği.

        wing_depth / center_depth oranı hesaplanır.
        Oran 1.0'a yaklaştıkça transit daha V-shaped görünür.
        """

        name = "v_shape_metric"

        if len(in_phase) < _MIN_INTRANSIT_POINTS:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.vshape_warn,
                fail_threshold=self.vshape_fail,
                description="Yetersiz transit içi nokta.",
            )

        depth = baseline - in_flux
        abs_phase = np.abs(in_phase)

        if np.all(~np.isfinite(depth)) or np.nanmax(abs_phase) <= 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.vshape_warn,
                fail_threshold=self.vshape_fail,
                description="V-shape metriği hesaplanamadı.",
            )

        q1 = np.quantile(abs_phase, 0.33)
        q2 = np.quantile(abs_phase, 0.67)

        center_mask = abs_phase <= q1
        wing_mask = abs_phase >= q2

        if np.sum(center_mask) < 2 or np.sum(wing_mask) < 2:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.vshape_warn,
                fail_threshold=self.vshape_fail,
                description="Center/wing bölgeleri oluşturulamadı.",
            )

        center_depth = float(np.median(depth[center_mask]))
        wing_depth = float(np.median(depth[wing_mask]))

        if center_depth <= 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.vshape_warn,
                fail_threshold=self.vshape_fail,
                description="Pozitif merkez derinliği bulunamadı.",
            )

        score = float(np.clip(wing_depth / center_depth, 0.0, 2.0))

        if score > self.vshape_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Transit belirgin V-shaped: "
                f"wing/center={score:.3f} > {self.vshape_fail:.3f}"
            )
        elif score > self.vshape_warn:
            verdict = VettingVerdict.WARN
            desc = f"V-shape uyarısı: wing/center={score:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Transit daha çok U-shaped/tutarlı: wing/center={score:.3f}"

        return TransitConsistencyTest(
            name=name,
            verdict=verdict,
            value=score,
            warn_threshold=self.vshape_warn,
            fail_threshold=self.vshape_fail,
            description=desc,
        )

    def _test_ingress_egress_symmetry(
        self,
        in_phase: np.ndarray,
        in_flux: np.ndarray,
        baseline: float,
    ) -> TransitConsistencyTest:
        """
        Ingress/egress simetri testi.

        Half-depth seviyesinde sol ve sağ tarafın extent farkı ölçülür:
            asym = |left_extent - right_extent| / max(left_extent, right_extent)
        """

        name = "ingress_egress_symmetry"

        if len(in_phase) < _MIN_INTRANSIT_POINTS:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.asym_warn,
                fail_threshold=self.asym_fail,
                description="Yetersiz transit içi nokta.",
            )

        depth = baseline - in_flux
        left_mask = in_phase < 0
        right_mask = in_phase > 0

        if np.sum(left_mask) < 2 or np.sum(right_mask) < 2:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.asym_warn,
                fail_threshold=self.asym_fail,
                description="Sol/sağ transit yarıları oluşturulamadı.",
            )

        peak_depth = float(np.nanmax(depth))
        if peak_depth <= 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.asym_warn,
                fail_threshold=self.asym_fail,
                description="Pozitif transit derinliği bulunamadı.",
            )

        half_depth = 0.5 * peak_depth

        left_extent_candidates = np.abs(in_phase[left_mask][depth[left_mask] >= half_depth])
        right_extent_candidates = np.abs(in_phase[right_mask][depth[right_mask] >= half_depth])

        if len(left_extent_candidates) == 0 or len(right_extent_candidates) == 0:
            return TransitConsistencyTest(
                name=name,
                verdict=VettingVerdict.SKIP,
                value=0.0,
                warn_threshold=self.asym_warn,
                fail_threshold=self.asym_fail,
                description="Half-depth extent ölçülemedi.",
            )

        left_extent = float(np.nanmax(left_extent_candidates))
        right_extent = float(np.nanmax(right_extent_candidates))

        scale = max(left_extent, right_extent, 1e-12)
        asym = abs(left_extent - right_extent) / scale

        if asym > self.asym_fail:
            verdict = VettingVerdict.FAIL
            desc = (
                f"Ingress/egress ciddi asimetrik: "
                f"{asym:.3f} > {self.asym_fail:.3f}"
            )
        elif asym > self.asym_warn:
            verdict = VettingVerdict.WARN
            desc = f"Ingress/egress asimetri uyarısı: {asym:.3f}"
        else:
            verdict = VettingVerdict.PASS
            desc = f"Ingress/egress simetrik: {asym:.3f}"

        return TransitConsistencyTest(
            name=name,
            verdict=verdict,
            value=float(asym),
            warn_threshold=self.asym_warn,
            fail_threshold=self.asym_fail,
            description=desc,
        )

    # ──────────────────────────────────────
    # Yardımcılar
    # ──────────────────────────────────────

    @staticmethod
    def _estimate_baseline(
        flux: np.ndarray,
        in_transit_mask: np.ndarray,
    ) -> float:
        """OOT median baseline tahmini."""

        oot = flux[~in_transit_mask]
        if len(oot) >= 5 and np.any(np.isfinite(oot)):
            return float(np.nanmedian(oot))

        if np.any(np.isfinite(flux)):
            return float(np.nanmedian(flux))

        return 1.0

    def _resolve_per_transit_depths(
        self,
        flux: np.ndarray,
        in_transit_mask: np.ndarray,
        transit_event_ids: Optional[np.ndarray],
        per_transit_depths: Optional[np.ndarray],
        baseline: float,
    ) -> np.ndarray:
        """
        Bireysel transit derinliklerini elde eder.

        Öncelik:
        1. Kullanıcı sağladıysa per_transit_depths
        2. event_ids varsa flux üzerinden tahmin et
        3. yoksa boş dizi döndür
        """

        if per_transit_depths is not None:
            arr = np.asarray(per_transit_depths, dtype=float)
            arr = arr[np.isfinite(arr) & (arr > 0)]
            return arr

        if transit_event_ids is None or len(transit_event_ids) != len(flux):
            return np.array([], dtype=float)

        depths: list[float] = []

        valid_ids = transit_event_ids[np.isfinite(transit_event_ids.astype(float))]
        if len(valid_ids) == 0:
            return np.array([], dtype=float)

        for event_id in np.unique(valid_ids):
            event_mask = transit_event_ids == event_id
            event_in = event_mask & in_transit_mask

            if np.sum(event_in) < 2:
                continue

            event_flux = flux[event_in]
            if not np.any(np.isfinite(event_flux)):
                continue

            event_depth = baseline - float(np.nanmedian(event_flux))
            if np.isfinite(event_depth) and event_depth > 0:
                depths.append(event_depth)

        return np.asarray(depths, dtype=float)

    @staticmethod
    def _compute_details(
        phase_in: np.ndarray,
        flux_in: np.ndarray,
        baseline: float,
        per_depths: np.ndarray,
    ) -> dict:
        """Downstream kullanım için ham detayları derler."""

        details: dict = {
            "n_intransit": len(phase_in),
            "n_transits": len(per_depths),
            "baseline": baseline,
        }

        if len(phase_in) > 0:
            depth = baseline - flux_in
            details["peak_depth"] = float(np.nanmax(depth))
            details["median_intransit_depth"] = float(np.nanmedian(depth))
            details["phase_span"] = float(np.nanmax(phase_in) - np.nanmin(phase_in))

        if len(per_depths) > 0:
            details["per_transit_depth_median"] = float(np.nanmedian(per_depths))
            details["per_transit_depth_std"] = float(np.nanstd(per_depths))
            details["per_transit_depth_min"] = float(np.nanmin(per_depths))
            details["per_transit_depth_max"] = float(np.nanmax(per_depths))

            if len(per_depths) >= 2:
                odd = per_depths[::2]
                even = per_depths[1::2]
                if len(odd) > 0:
                    details["odd_depth_median"] = float(np.nanmedian(odd))
                if len(even) > 0:
                    details["even_depth_median"] = float(np.nanmedian(even))

        return details

    @staticmethod
    def _compute_score(
        tests: list[TransitConsistencyTest],
    ) -> float:
        """
        Ağırlıklı anomaly skoru.

        FAIL = 1.0
        WARN = 0.4
        PASS = 0.0
        SKIP = dahil edilmez
        """

        weights = {
            "even_odd_depth_consistency": 0.30,
            "transit_repeatability": 0.30,
            "v_shape_metric": 0.25,
            "ingress_egress_symmetry": 0.15,
        }

        active = [t for t in tests if t.verdict != VettingVerdict.SKIP]
        if not active:
            return 0.0

        score_map = {
            VettingVerdict.FAIL: 1.0,
            VettingVerdict.WARN: 0.4,
            VettingVerdict.PASS: 0.0,
        }

        denom = 0.0
        total = 0.0

        for test in active:
            w = weights.get(test.name, 0.25)
            denom += w
            total += w * score_map.get(test.verdict, 0.0)

        if denom <= 0:
            return 0.0

        return float(np.clip(total / denom, 0.0, 1.0))

    @staticmethod
    def _compute_flag(
        tests: list[TransitConsistencyTest],
        score: float,
        n_fail: int,
        n_warn: int,
    ) -> str:
        """
        Genel transit consistency bayrağı.

        CONSISTENT : score < 0.25 ve fail yok
        VARIABLE   : orta seviye tutarsızlık
        EB_SUSPECT : güçlü even/odd veya V-shape problemi
        """

        fail_names = {
            t.name for t in tests
            if t.verdict == VettingVerdict.FAIL
        }

        if (
            "even_odd_depth_consistency" in fail_names
            or "v_shape_metric" in fail_names
            or n_fail >= 2
            or score >= 0.60
        ):
            return "EB_SUSPECT"

        if n_fail == 1 or n_warn >= 2 or score >= 0.25:
            return "VARIABLE"

        return "CONSISTENT"