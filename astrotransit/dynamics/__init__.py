"""
Dinamik katman: Lagrange noktaları (L1) ve CR3BP yörünge dinamiği.

Bu paket iki keşif kolunun ortak teknik altyapısıdır:
- Kol 1: L1 çevresinde Dünya-benzeri, yaşanabilir gezegen adayı
- Kol 2: L1 noktasında yörüngesi kontrol edilebilen uydu / mega yapı

Epistemik not: Kolineer Lagrange noktaları (L1/L2/L3) doğal olarak
kararsızdır. Bu paket bu gerçeği hesaplar; "orada kalıcı cisim var"
iddiasının kontrol gerektirdiğini ima eder, kanıtlamaz.
"""

from astrotransit.dynamics.cr3bp import (
    cr3bp_rhs,
    integrate_orbit,
    l1_eigenvalues,
    l1_linearized_matrix,
    linear_lissajous_state,
    stability_e_folding_days,
    station_keeping_budget,
    station_keeping_delta_v_per_correction,
)
from astrotransit.dynamics.lagrange import (
    collinear_equilibrium_x,
    lagrange_point_positions,
    mass_ratio,
)
from astrotransit.dynamics.system import (
    L1Assessment,
    L1System,
    assess_l1,
)

__all__ = [
    "L1Assessment",
    "L1System",
    "assess_l1",
    "collinear_equilibrium_x",
    "cr3bp_rhs",
    "integrate_orbit",
    "l1_eigenvalues",
    "l1_linearized_matrix",
    "lagrange_point_positions",
    "linear_lissajous_state",
    "mass_ratio",
    "stability_e_folding_days",
    "station_keeping_budget",
    "station_keeping_delta_v_per_correction",
]
