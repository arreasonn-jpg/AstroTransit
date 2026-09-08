"""
Transit tespit eşik değerleri ve kalite kriterleri.

BLS ve TLS sonuçlarını değerlendirmek için kullanılan
eşik değerleri bu modülde merkezi olarak tanımlanır.
Tüm eşikler kullanıcı tarafından ayarlanabilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger


@dataclass
class BLSThresholds:
    """
    BLS arama eşik değerleri.

    Attributes
    ----------
    min_power : float
        Minimum BLS güç eşiği (SDE).
        Literatür referansı: Kovacs et al. 2002
        Tipik değer: 6.0 – 9.0
    min_depth : float
        Minimum transit derinliği (göreli birim).
        0.0001 = 100 ppm
    max_depth : float
        Maksimum transit derinliği.
        0.5 = yüzde elli (EB sınırı).
    min_duration_days : float
        Minimum transit süresi (gün).
    max_duration_days : float
        Maksimum transit süresi (gün).
    min_period_days : float
        Minimum arama periyodu (gün).
    max_period_days : float
        Maksimum arama periyodu (gün).
    min_transits : int
        Minimum transit sayısı.
    """

    min_power: float = 7.0
    min_depth: float = 1e-4
    max_depth: float = 0.5
    min_duration_days: float = 0.01
    max_duration_days: float = 0.5
    min_period_days: float = 0.3
    max_period_days: float = 30.0
    min_transits: int = 2

    def validate(self) -> None:
        """Eşik değerlerinin tutarlılığını kontrol eder."""

        if self.min_period_days >= self.max_period_days:
            raise ValueError(
                f"min_period ({self.min_period_days}) >= "
                f"max_period ({self.max_period_days})"
            )
        if self.min_depth >= self.max_depth:
            raise ValueError(
                f"min_depth ({self.min_depth}) >= "
                f"max_depth ({self.max_depth})"
            )
        if self.min_duration_days >= self.max_duration_days:
            raise ValueError(
                f"min_duration ({self.min_duration_days}) >= "
                f"max_duration ({self.max_duration_days})"
            )
        if self.min_transits < 2:
            raise ValueError(
                f"min_transits ({self.min_transits}) < 2. "
                f"En az 2 geçiş gereklidir."
            )


@dataclass
class TLSThresholds:
    """
    TLS doğrulama eşik değerleri.

    Attributes
    ----------
    min_sde : float
        Minimum Signal Detection Efficiency.
        Literatür referansı: Hippke & Heller 2019
        Tipik değer: 6.0 – 8.0
    min_snr : float
        Minimum sinyal-gürültü oranı.
    max_false_alarm : float
        Maksimum yanlış alarm olasılığı.
    min_transit_count : int
        Minimum onaylı transit sayısı.
    min_odd_even_mismatch : float
        Tek-çift transit derinlik farkı için alt sınır.
        Bu değerin ALTI beklenir (yüksekse EB şüphesi).
    max_odd_even_mismatch : float
        Bu değerin ÜZERİNDE EB şüphesi artar.
    """

    min_sde: float = 6.0
    min_snr: float = 5.0
    max_false_alarm: float = 0.1
    min_transit_count: int = 2
    max_odd_even_mismatch: float = 3.0

    def validate(self) -> None:
        """Eşik değerlerinin tutarlılığını kontrol eder."""

        if self.min_sde < 0:
            raise ValueError(f"min_sde negatif olamaz: {self.min_sde}")
        if not 0.0 < self.max_false_alarm <= 1.0:
            raise ValueError(
                f"max_false_alarm 0-1 arasında olmalı: {self.max_false_alarm}"
            )


@dataclass
class CascadeThresholds:
    """
    BLS → TLS kademeli sistemin karar eşikleri.

    Attributes
    ----------
    require_both : bool
        Hem BLS hem TLS onayı zorunlu mu?
    period_tolerance : float
        BLS ve TLS periyotları arasındaki maksimum göreli fark.
        |P_BLS - P_TLS| / P_BLS < period_tolerance
    depth_tolerance : float
        Transit derinliği göreli fark toleransı.
    bls : BLSThresholds
        BLS eşikleri.
    tls : TLSThresholds
        TLS eşikleri.
    """

    require_both: bool = True
    period_tolerance: float = 0.01
    depth_tolerance: float = 0.5
    bls: BLSThresholds = field(default_factory=BLSThresholds)
    tls: TLSThresholds = field(default_factory=TLSThresholds)

    def validate(self) -> None:
        """Tüm eşikleri doğrular."""

        self.bls.validate()
        self.tls.validate()

        if not 0.0 < self.period_tolerance < 0.5:
            raise ValueError(
                f"period_tolerance 0-0.5 arasında olmalı: {self.period_tolerance}"
            )

    @classmethod
    def from_settings(cls, settings) -> "CascadeThresholds":
        """Settings nesnesinden CascadeThresholds oluşturur."""

        det = settings.detection

        bls = BLSThresholds(
            min_power=det.bls.min_power_threshold,
            min_duration_days=det.bls.duration_range[0],
            max_duration_days=det.bls.duration_range[1],
            min_period_days=det.min_period,
            max_period_days=det.max_period,
            min_transits=det.min_transits,
        )

        tls = TLSThresholds(
            min_sde=det.tls.min_sde_threshold,
        )

        cascade = cls(
            require_both=det.cascade.require_both,
            period_tolerance=det.cascade.period_tolerance,
            bls=bls,
            tls=tls,
        )

        cascade.validate()

        logger.debug(
            f"CascadeThresholds yüklendi — "
            f"BLS min_power: {bls.min_power}, "
            f"TLS min_sde: {tls.min_sde}, "
            f"periyot toleransı: {cascade.period_tolerance}"
        )

        return cascade