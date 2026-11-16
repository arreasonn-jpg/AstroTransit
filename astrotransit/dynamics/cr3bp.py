"""
CR3BP (dairesel kısıtlı üç-cisim problemi) yörünge dinamiği ve L1 kararlılığı.

Dönen koordinatlarda denklem:
    x'' = 2 y' + x - (1-mu)(x+mu)/r1^3 - mu(x-1+mu)/r2^3
    y'' = -2 x' + y - (1-mu)y/r1^3 - mu y/r2^3

Birim zaman: ortalama hareket n = 1 (periyot 2*pi birim).

L1 civarında doğrusallaştırılmış sistemin özdeğerleri bir reel çift ve iki
kompleks çift içerir; pozitif reel özdeğer kararsız (üstel) modu verir.
Kararlılık e-katlama süresi: t_e = 1 / lambda_unstable (birim zaman), gün
cinsine çevrilir.

Epistemik not: L1 doğal olarak kararsızdır. Bir cismin L1'de "görülmesi"
onun kontrol edilmediğini göstermez; ama kontrolsüz bir cisim L1'de uzun
süre kalamaz. Bu modül yalnızca dinamiği hesaplar, "kontrol var" iddiasını
kanıtlamaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

from astrotransit.dynamics.lagrange import (
    DAY_S,
    collinear_equilibrium_x,
)

# Birim-zaman -> gün dönüşümü: CR3BP'de n = sqrt(G(M)/a^3); birim zaman
# 1/n saniye olur. Bu dönüşüm assess katmanında separation ile yapılır.


def cr3bp_rhs(t: float, state: np.ndarray, mu: float) -> np.ndarray:
    """CR3BP sağ tarafı. state = [x, y, vx, vy]; t kullanılmaz (otonom)."""
    x, y, vx, vy = state
    r1 = math.sqrt((x + mu) ** 2 + y ** 2)
    r2 = math.sqrt((x - 1.0 + mu) ** 2 + y ** 2)
    ax = 2.0 * vy + x - (1.0 - mu) * (x + mu) / r1 ** 3 - mu * (x - 1.0 + mu) / r2 ** 3
    ay = -2.0 * vx + y - (1.0 - mu) * y / r1 ** 3 - mu * y / r2 ** 3
    return np.array([vx, vy, ax, ay])


def integrate_orbit(
    mu: float,
    initial_state: np.ndarray,
    duration: float,
    n_points: int = 1000,
    rtol: float = 1e-9,
    atol: float = 1e-12,
) -> dict[str, np.ndarray]:
    """CR3BP yörüngesini entegre eder.

    duration birim zamandır (2*pi = bir tam yörünge periyodu).
    Dönüş: t, x, y, vx, vy dizileri.
    """
    if duration <= 0.0:
        raise ValueError("Süre pozitif olmalıdır.")
    t_eval = np.linspace(0.0, duration, n_points)
    sol = solve_ivp(
        cr3bp_rhs,
        (0.0, duration),
        np.asarray(initial_state, dtype=float),
        args=(mu,),
        t_eval=t_eval,
        rtol=rtol,
        atol=atol,
        method="DOP853",
    )
    if not sol.success:
        raise RuntimeError(f"Entegrasyon başarısız: {sol.message}")
    return {
        "t": sol.t,
        "x": sol.y[0],
        "y": sol.y[1],
        "vx": sol.y[2],
        "vy": sol.y[3],
    }


def l1_linearized_matrix(mu: float) -> np.ndarray:
    """L1 noktasında doğrusallaştırılmış 4x4 sistem matrisi A.

    Durum vektörü [dx, dy, dvx, dvy]; A = [[0,0,1,0],[0,0,0,1],[Uxx, Uxy, 0, 2],[Uyx, Uyy, -2, 0]]
    """
    x_l1 = collinear_equilibrium_x(mu, "L1")
    r1 = abs(x_l1 + mu)
    r2 = abs(x_l1 - 1.0 + mu)
    u_xx = 1.0 + 2.0 * (1.0 - mu) / r1 ** 3 + 2.0 * mu / r2 ** 3
    u_yy = 1.0 - (1.0 - mu) / r1 ** 3 - mu / r2 ** 3
    u_xy = 0.0  # kolinear noktalarda
    a = np.array(
        [
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0],
            [u_xx, u_xy, 0.0, 2.0],
            [u_xy, u_yy, -2.0, 0.0],
        ]
    )
    return a


def l1_eigenvalues(mu: float) -> np.ndarray:
    """L1 doğrusal sistemin özdeğerleri (karmaşık)."""
    return np.linalg.eigvals(l1_linearized_matrix(mu))


def stability_e_folding_days(mu: float, mean_motion_per_day: float) -> float | None:
    """Kararsız modun e-katlama süresi (gün).

    mean_motion_per_day: n [rad/gün] = 2*pi / periyot_gün. Birim zaman
    1/n gün olduğundan t_e(gün) = (1/lambda_max) / n_per_day.
    Kararsız reel özdeğer yoksa None döner (bu pratikte olmaz).
    """
    if mean_motion_per_day <= 0.0:
        raise ValueError("Ortalama hareket pozitif olmalıdır.")
    eigs = l1_eigenvalues(mu)
    real_parts = eigs.real
    lam_max = float(np.max(real_parts))
    if lam_max <= 0.0:
        return None
    return 1.0 / (lam_max * mean_motion_per_day)


def linear_lissajous_state(mu: float, amplitude: float, phase: float = 0.0) -> np.ndarray:
    """L1 civarında küçük genlikli Lissajous (quasi-halo) başlangıç durumu.

    Basit yaklaşım: kararsız mod yok sayılarak, merkez L1'de, x yönünde
    genlik `amplitude`, faz `phase` ile salınım:
    state = [x_L1 + amplitude*cos(phase), 0, -amplitude*sin(phase)*w, 0]
    Not: bu bir başlangıç tahminidir; gerçek Lissajous yörüngeleri
    sayısal düzeltme (differential correction) gerektirir.
    """
    if amplitude <= 0.0:
        raise ValueError("Genlik pozitif olmalıdır.")
    x_l1 = collinear_equilibrium_x(mu, "L1")
    w = math.sqrt(abs(1.0 - (1.0 - mu) / abs(x_l1 + mu) ** 3 - mu / abs(x_l1 - 1.0 + mu) ** 3))
    return np.array(
        [
            x_l1 + amplitude * math.cos(phase),
            0.0,
            -amplitude * math.sin(phase) * w,
            0.0,
        ]
    )


def station_keeping_delta_v_per_correction(
    e_folding_days: float,
    correction_interval_days: float,
    amplitude: float,
) -> float:
    """Tek bir yörünge düzeltmesinin gerektirdiği delta-v (birim hız).

    Model: kararsız mod her e-katlama süresinde genliği e katına çıkarır.
    Düzeltme anında sapma `amplitude`'a ulaşmışsa, onu sıfırlamak için
    gereken hız atımı ~ amplitude * lambda (birim hız birimi: a*n).
    """
    if e_folding_days <= 0.0 or correction_interval_days <= 0.0 or amplitude <= 0.0:
        raise ValueError("Parametreler pozitif olmalıdır.")
    lam = 1.0 / e_folding_days  # birim zamandaki büyüme oranı
    return amplitude * lam


def station_keeping_budget(
    e_folding_days: float,
    mission_days: float,
    correction_interval_days: float,
    amplitude: float,
) -> dict[str, float]:
    """Görev süresi boyunca istasyon tutma delta-v bütçesi.

    Dönüş: düzeltme sayısı, düzeltme başına delta-v, toplam delta-v
    (hepsi birim hız a*n cinsinden; gerçek m/s için a*n ile çarpılır).
    """
    if mission_days <= 0.0:
        raise ValueError("Görev süresi pozitif olmalıdır.")
    n_corr = math.ceil(mission_days / correction_interval_days)
    per_corr = station_keeping_delta_v_per_correction(e_folding_days, correction_interval_days, amplitude)
    return {
        "n_corrections": float(n_corr),
        "delta_v_per_correction": per_corr,
        "total_delta_v": per_corr * n_corr,
    }


@dataclass(frozen=True)
class OrbitSummary:
    """Entegre edilmiş yörüngenin özeti."""

    duration: float
    final_distance_from_l1: float
    max_distance_from_l1: float
    n_points: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "duration": round(self.duration, 4),
            "final_distance_from_l1": round(self.final_distance_from_l1, 6),
            "max_distance_from_l1": round(self.max_distance_from_l1, 6),
            "n_points": self.n_points,
        }


def summarize_orbit(mu: float, orbit: dict[str, np.ndarray]) -> OrbitSummary:
    """Yörüngenin L1'e olan mesafesi istatistiklerini üretir."""
    x_l1 = collinear_equilibrium_x(mu, "L1")
    dx = orbit["x"] - x_l1
    dy = orbit["y"]
    dist = np.sqrt(dx ** 2 + dy ** 2)
    return OrbitSummary(
        duration=float(orbit["t"][-1]),
        final_distance_from_l1=float(dist[-1]),
        max_distance_from_l1=float(np.max(dist)),
        n_points=len(orbit["t"]),
    )


def day_to_unit_time(mean_motion_per_day: float) -> float:
    """1 günün birim zamandaki karşılığı: n (rad/gün) birim-zaman/gün."""
    if mean_motion_per_day <= 0.0:
        raise ValueError("Ortalama hareket pozitif olmalıdır.")
    return mean_motion_per_day


def unit_time_to_days(unit_time: float, mean_motion_per_day: float) -> float:
    """Birim zamanın gün karşılığı."""
    if mean_motion_per_day <= 0.0:
        raise ValueError("Ortalama hareket pozitif olmalıdır.")
    return unit_time / mean_motion_per_day


__all__ = [
    "DAY_S",
    "OrbitSummary",
    "cr3bp_rhs",
    "day_to_unit_time",
    "integrate_orbit",
    "l1_eigenvalues",
    "l1_linearized_matrix",
    "linear_lissajous_state",
    "stability_e_folding_days",
    "station_keeping_budget",
    "station_keeping_delta_v_per_correction",
    "summarize_orbit",
    "unit_time_to_days",
]
