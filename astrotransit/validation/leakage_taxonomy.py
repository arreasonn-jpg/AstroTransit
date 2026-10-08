"""Adversarial FP leakage taxonomy.

Bu modül, adversarial FP korpusunda ``leaked_as_candidate`` olarak sonuçlanan
senaryoları sınıflandırır. Amaç: "10 FP kaçtı" ifadesini bilimsel olarak
anlamlı bir sınıflandırmaya dönüştürmek. Örneğin:

    "FP kaçışlarının %60'ı düşük transit sayısından kaynaklanıyor."

Bu, hangi vetting testinin hangi koşulda zayıf kaldığını gösterir ve
iyileştirmeyi hedefe yönlendirir.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Optional

#: Kategorik taksonomi. Yeni kategori eklerken hem burayı hem de
#: ``classify_leak`` fonksiyonunu güncelle.
LEAKAGE_CATEGORIES = (
    "LOW_TRANSIT_COUNT",
    "WEAK_SECONDARY",
    "WEAK_ODD_EVEN",
    "V_SHAPE",
    "GRAZING",
    "DURATION_ANOMALY",
    "STELLAR_VARIABILITY",
    "HARMONIC_CONFUSION",
    "BLENDING",
    "OTHER",
)


def classify_leak(row: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Bir leak satırını kategoriye ve tetikleyicilere ayırır.

    Returns
    -------
    (category, reasons)
        ``category`` — birincil taksonomik kategori
        ``reasons`` — sınıflandırmayı tetikleyen gözlemlerin listesi

    Öncelik sırası bilinçlidir: en somut/güçlü gözlem en üstte.
    """
    reasons: list[str] = []

    # Sayısal alanları güvenli biçimde çek
    def _num(*names: str) -> Optional[float]:
        for n in names:
            v = row.get(n)
            if v is None:
                continue
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
        return None

    transits = _num("n_transits", "number_of_transits", "transit_count")
    depth_variance = _num("depth_variance")
    odd_even = _num("odd_even_mismatch", "odd_even")
    secondary = _num("secondary_eclipse_depth_ppm", "secondary_eclipse_depth")
    symmetry = _num("transit_symmetry")
    duration_hours = _num("duration_hours")
    period_days = _num("period_days")
    variability = _num("variability_amplitude_ppm", "variability_amplitude")
    dilution = _num("dilution")
    steepness = _num("steepness")

    # 1) Harmonik karışıklık: period 2P veya P/2 olarak raporlanmış
    if row.get("harmonic_confusion") is True:
        return "HARMONIC_CONFUSION", ["harmonic_confusion flag set"]

    # 2) Düşük transit sayısı (≤ 5) — morphology zayıf
    if transits is not None and transits <= 5:
        reasons.append(f"n_transits={transits:.0f} (low; morphology weak)")
        # Diğer testler de zayıfsa LOW_TRANSIT_COUNT birincil
        secondary_weak = secondary is None or abs(secondary) < 500
        odd_even_weak = odd_even is None or abs(odd_even) < 1.5
        if secondary_weak and odd_even_weak:
            return "LOW_TRANSIT_COUNT", reasons

    # 3) V şekli: steepness yüksek (1.0 = tam üçgen)
    if steepness is not None and steepness >= 0.9:
        return "V_SHAPE", [f"steepness={steepness:.2f} (triangular profile)"]

    # 4) Zayıf ikincil
    if secondary is not None and abs(secondary) < 100:
        return "WEAK_SECONDARY", [f"secondary_eclipse_depth={secondary:.1f} ppm (weak)"]

    # 5) Zayıf odd/even
    if odd_even is not None and abs(odd_even) < 1.0:
        return "WEAK_ODD_EVEN", [f"odd_even_mismatch={odd_even:.2f} (weak)"]

    # 6) Duration anomalisi
    if duration_hours is not None and period_days is not None:
        ratio = duration_hours / (period_days * 24.0)
        if ratio > 0.2 or ratio < 0.01:
            return "DURATION_ANOMALY", [f"duration/period={ratio:.3f}"]

    # 7) Yıldız değişkenliği
    if variability is not None and variability > 1000:
        return "STELLAR_VARIABILITY", [f"variability_amplitude={variability:.0f} ppm"]

    # 8) Blending / dilution
    if dilution is not None and dilution < 0.5:
        return "BLENDING", [f"dilution={dilution:.2f} (< 0.5)"]

    # 9) Grazing: depth variance yüksek
    if depth_variance is not None and depth_variance > 0.1:
        return "GRAZING", [f"depth_variance={depth_variance:.3f}"]

    # 10) Simetri bozukluğu
    if symmetry is not None and abs(symmetry) > 0.3:
        return "OTHER", [f"transit_symmetry={symmetry:.3f} (asymmetric)"]

    return "OTHER", reasons or ["no specific trigger matched"]


def summarize_leaks(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Tüm leak satırları için kategori dağılımını özetler.

    Returns
    -------
    dict with keys:
        ``total``: toplam leak sayısı
        ``by_category``: kategori → adet
        ``by_family``: aile → adet
        ``details``: her leak için ayrıntılı sınıflandırma
    """
    leak_rows = [
        r
        for r in rows
        if str(r.get("outcome")) == "leaked_as_candidate"
        and str(r.get("family", "")) != "planetary_control"
    ]
    counter: Counter[str] = Counter()
    by_family: Counter[str] = Counter()
    details = []

    for row in leak_rows:
        category, reasons = classify_leak(row)
        counter[category] += 1
        by_family[str(row.get("family", "unknown"))] += 1
        details.append(
            {
                "scenario_id": row.get("scenario_id"),
                "family": row.get("family"),
                "category": category,
                "reasons": reasons,
                "fpp": row.get("fpp"),
                "n_transits": row.get("n_transits") or row.get("number_of_transits"),
                "depth_ppm": row.get("depth_ppm") or row.get("depth"),
                "snr": row.get("snr"),
            }
        )

    total = len(leak_rows)
    by_cat = dict(counter.most_common())
    percentages = {k: (100.0 * v / total if total else 0.0) for k, v in by_cat.items()}

    return {
        "total": total,
        "by_category": by_cat,
        "by_category_percent": {k: round(v, 2) for k, v in percentages.items()},
        "by_family": dict(by_family.most_common()),
        "details": details,
    }


__all__ = ["LEAKAGE_CATEGORIES", "classify_leak", "summarize_leaks"]
