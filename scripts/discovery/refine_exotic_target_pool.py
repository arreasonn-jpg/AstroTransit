#!/usr/bin/env python3
"""
Geniş non-TOI target pool içinden yeni egzotik/hedef odaklı yıldız havuzu üretir.

Temalar
-------
- TEMPERATE_SMALL_STRICT
- TEMPERATE_SMALL_HOST
- GIANT_HZ_HOST_SYSTEM
- HZ_ACCESSIBLE_COOL_STAR
- LOW_PRIORITY
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger


_SOLAR_TEFF_K = 5772.0


def _first_valid(row: pd.Series, names: list[str], default=None):
    # 1) exact match
    for name in names:
        if name in row.index:
            val = row[name]
            if pd.notna(val):
                return val

    # 2) case-insensitive match
    lowered = {str(col).strip().lower(): col for col in row.index}
    for name in names:
        key = str(name).strip().lower()
        if key in lowered:
            real_col = lowered[key]
            val = row[real_col]
            if pd.notna(val):
                return val

    return default


def _to_float(x, default=None):
    try:
        if x is None:
            return default
        x = float(x)
        if not np.isfinite(x):
            return default
        return x
    except Exception:
        return default


def _to_int(x, default=0):
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default


def estimate_luminosity_lsun(radius_rsun: float | None, teff_k: float | None) -> float | None:
    if radius_rsun is None or teff_k is None or radius_rsun <= 0 or teff_k <= 0:
        return None
    return float((radius_rsun ** 2) * ((teff_k / _SOLAR_TEFF_K) ** 4))


def hz_center_au(lum_lsun: float | None) -> float | None:
    if lum_lsun is None or lum_lsun <= 0:
        return None
    return float(np.sqrt(lum_lsun))


def estimate_mass_msun(
    mass_msun: float | None,
    radius_rsun: float | None,
    teff_k: float | None,
    lum_lsun: float | None,
) -> float | None:
    """
    Eğer doğrudan stellar mass yoksa kaba bir dwarf-host tahmini yap.
    Bu yalnızca HZ merkez periyodu önceliklendirmesi için kullanılır.
    """
    if mass_msun is not None and mass_msun > 0:
        return float(mass_msun)

    if radius_rsun is not None and radius_rsun > 0:
        r = float(radius_rsun)
        if 0.15 <= r <= 1.5:
            return float(np.clip(r ** 0.95, 0.12, 1.6))

    if lum_lsun is not None and lum_lsun > 0:
        l = float(lum_lsun)
        return float(np.clip(l ** 0.25, 0.12, 1.8))

    if teff_k is not None and teff_k > 0:
        t = float(teff_k)
        if t < 3600:
            return 0.3
        if t < 4200:
            return 0.5
        if t < 5000:
            return 0.75
        if t < 5800:
            return 0.95
        if t < 6500:
            return 1.15
        return 1.3

    return None


def orbital_period_days(a_au: float | None, mstar_msun: float | None) -> float | None:
    if a_au is None or mstar_msun is None or a_au <= 0 or mstar_msun <= 0:
        return None
    years = np.sqrt((a_au ** 3) / mstar_msun)
    return float(years * 365.25)


def _extract_sector_count(row: pd.Series) -> int:
    val = _first_valid(row, [
        "sector_count", "n_sectors", "num_sectors", "sector_n",
        "sectors_count", "sector_count_resolved"
    ], default=None)
    if val is not None:
        return _to_int(val, default=0)

    sectors = _first_valid(row, ["sectors", "sector_list"], default=None)
    if sectors is None:
        return 0

    if isinstance(sectors, str):
        s = sectors.strip()
        if not s:
            return 0
        for delim in ["|", ",", ";", " "]:
            if delim in s:
                parts = [p for p in s.replace("[", "").replace("]", "").split(delim) if p.strip()]
                if parts:
                    return len(parts)
        return 1

    return 0


def _score_brightness(tmag: float | None) -> float:
    if tmag is None:
        return 0.0
    if tmag <= 8.0:
        return 100.0
    if tmag <= 9.0:
        return 85.0
    if tmag <= 10.0:
        return 70.0
    if tmag <= 10.5:
        return 60.0
    if tmag <= 11.0:
        return 50.0
    if tmag <= 12.0:
        return 35.0
    return 15.0


def _score_sector_coverage(nsec: int) -> float:
    if nsec >= 8:
        return 100.0
    if nsec >= 5:
        return 85.0
    if nsec >= 3:
        return 65.0
    if nsec >= 2:
        return 40.0
    return 10.0


def _score_hz_accessibility(hz_period_days: float | None, max_detectable_period: float) -> float:
    if hz_period_days is None or hz_period_days <= 0:
        return 0.0

    p = float(hz_period_days)

    if p <= max_detectable_period * 0.5:
        return 100.0
    if p <= max_detectable_period * 0.75:
        return 80.0
    if p <= max_detectable_period:
        return 60.0
    if p <= max_detectable_period * 1.25:
        return 35.0
    if p <= max_detectable_period * 1.5:
        return 20.0
    return 5.0


def _score_cool_small_star(teff: float | None, radius: float | None) -> float:
    if teff is None or radius is None:
        return 0.0

    score = 0.0
    if 2800 <= teff <= 4300:
        score += 65.0
    elif 4300 < teff <= 5000:
        score += 35.0
    elif 5000 < teff <= 5600:
        score += 10.0

    if 0.10 <= radius <= 0.75:
        score += 35.0
    elif 0.75 < radius <= 0.90:
        score += 20.0
    elif 0.90 < radius <= 1.05:
        score += 5.0

    return float(np.clip(score, 0.0, 100.0))


def _score_giant_hz_system(teff: float | None, radius: float | None, hz_period_days: float | None) -> float:
    if teff is None or radius is None:
        return 0.0

    score = 0.0

    if 3500 <= teff <= 6200:
        score += 50.0
    elif 6200 < teff <= 6800:
        score += 20.0

    if 0.5 <= radius <= 1.3:
        score += 35.0
    elif 1.3 < radius <= 1.8:
        score += 15.0

    if hz_period_days is not None:
        if hz_period_days <= 120:
            score += 15.0
        elif hz_period_days <= 180:
            score += 8.0

    return float(np.clip(score, 0.0, 100.0))


def _score_strict_temperate_access(
    teff: float | None,
    radius: float | None,
    tmag: float | None,
    nsec: int,
    hz_period_days: float | None,
) -> float:
    """
    Gerçekten TESS ile erişilebilir HZ-benzeri küçük yıldız hedefleri için
    daha sert skor.
    """
    if teff is None or radius is None or hz_period_days is None:
        return 0.0

    score = 0.0

    # küçük ve serin yıldız
    if teff <= 3800:
        score += 35.0
    elif teff <= 4300:
        score += 28.0
    elif teff <= 4600:
        score += 15.0

    if radius <= 0.60:
        score += 30.0
    elif radius <= 0.75:
        score += 24.0
    elif radius <= 0.85:
        score += 10.0

    # HZ gerçekten TESS erişiminde mi?
    p = float(hz_period_days)
    if p <= 25:
        score += 30.0
    elif p <= 35:
        score += 24.0
    elif p <= 40:
        score += 18.0
    elif p <= 50:
        score += 8.0

    # tekrar gözlem avantajı
    if nsec >= 5:
        score += 15.0
    elif nsec >= 3:
        score += 10.0
    elif nsec >= 2:
        score += 4.0

    # parlaklık
    if tmag is not None:
        if tmag <= 9.0:
            score += 10.0
        elif tmag <= 10.5:
            score += 7.0
        elif tmag <= 11.0:
            score += 4.0

    return float(np.clip(score, 0.0, 100.0))


def classify_theme(
    teff: float | None,
    radius: float | None,
    mass: float | None,
    tmag: float | None,
    lum: float | None,
    hz_a: float | None,
    hz_period_days: float | None,
    nsec: int,
    theme_mode: str,
) -> tuple[str, float, str]:
    """
    Returns
    -------
    (theme, target_score, reason)
    """

    bright_score = _score_brightness(tmag)
    sector_score = _score_sector_coverage(nsec)
    hz_access_50 = _score_hz_accessibility(hz_period_days, 50.0)
    hz_access_60 = _score_hz_accessibility(hz_period_days, 60.0)
    hz_access_120 = _score_hz_accessibility(hz_period_days, 120.0)
    cool_score = _score_cool_small_star(teff, radius)
    giant_score = _score_giant_hz_system(teff, radius, hz_period_days)
    strict_score = _score_strict_temperate_access(teff, radius, tmag, nsec, hz_period_days)

    temperate_small_score = (
        0.35 * cool_score +
        0.35 * hz_access_60 +
        0.15 * bright_score +
        0.15 * sector_score
    )

    giant_hz_score = (
        0.30 * giant_score +
        0.35 * hz_access_120 +
        0.15 * bright_score +
        0.20 * sector_score
    )

    strict_gate = (
        teff is not None and teff <= 4300 and
        radius is not None and radius <= 0.75 and
        hz_period_days is not None and hz_period_days <= 40.0 and
        nsec >= 3 and
        (tmag is None or tmag <= 10.5)
    )

    strict_soft_gate = (
        teff is not None and teff <= 4600 and
        radius is not None and radius <= 0.85 and
        hz_period_days is not None and hz_period_days <= 55.0 and
        nsec >= 2
    )

    if theme_mode == "temperate-small-strict":
        if strict_gate and strict_score >= 60:
            return (
                "TEMPERATE_SMALL_STRICT",
                float(strict_score),
                "Strict TESS-detectable temperate small-host criteria satisfied."
            )
        if strict_soft_gate:
            return (
                "HZ_ACCESSIBLE_COOL_STAR",
                float(max(strict_score, temperate_small_score)),
                "Cool-star HZ is partially accessible, but strict criteria are not fully met."
            )
        return (
            "LOW_PRIORITY",
            float(strict_score),
            "Does not satisfy strict TESS-detectable temperate small-host criteria."
        )

    if theme_mode == "temperate-small":
        if temperate_small_score >= 55:
            return "TEMPERATE_SMALL_HOST", float(temperate_small_score), "Small/cool star with comparatively accessible HZ."
        if hz_access_60 >= 40 and cool_score >= 40:
            return "HZ_ACCESSIBLE_COOL_STAR", float(temperate_small_score), "HZ is at least partly accessible around a cool star."
        return "LOW_PRIORITY", float(temperate_small_score), "HZ around this star is not especially accessible for a small-world campaign."

    if theme_mode == "giant-hz":
        if giant_hz_score >= 55:
            return "GIANT_HZ_HOST_SYSTEM", float(giant_hz_score), "Star is favorable for detecting temperate giant/HZ-host systems."
        return "LOW_PRIORITY", float(giant_hz_score), "Not especially favorable for giant-HZ-host discovery."

    # auto
    if strict_gate and strict_score >= 60:
        return "TEMPERATE_SMALL_STRICT", float(strict_score), "Auto-selected under strict TESS-detectable temperate criteria."
    if temperate_small_score >= 62:
        return "TEMPERATE_SMALL_HOST", float(temperate_small_score), "Auto-selected as temperate-small target."
    if giant_hz_score >= 58:
        return "GIANT_HZ_HOST_SYSTEM", float(giant_hz_score), "Auto-selected as giant-HZ-host target."
    if hz_access_50 >= 45 and cool_score >= 35:
        return "HZ_ACCESSIBLE_COOL_STAR", float(max(strict_score, temperate_small_score)), "HZ likely reachable in a cool-star system."
    return "LOW_PRIORITY", float(max(strict_score, temperate_small_score, giant_hz_score)), "Not strongly prioritized for exotic/HZ search."


def main():
    parser = argparse.ArgumentParser(description="Refine exotic target pool")
    parser.add_argument("--input", required=True, help="Input CSV/parquet")
    parser.add_argument("--output", required=True, help="Output CSV/parquet path")
    parser.add_argument(
        "--theme",
        choices=["auto", "temperate-small", "temperate-small-strict", "giant-hz"],
        default="auto",
        help="Target theme",
    )
    parser.add_argument("--max-targets", type=int, default=500, help="Maximum output targets")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    if input_path.suffix.lower() == ".parquet":
        df = pd.read_parquet(input_path)
    else:
        df = pd.read_csv(input_path)

    logger.info(f"Girdi yüklendi: {input_path} | satır={len(df)}")

    rows = []
    for _, row in df.iterrows():
        teff = _to_float(_first_valid(row, [
            "stellar_teff", "teff_k", "teff", "Teff", "TEFF", "star_teff", "st_teff"
        ]))
        radius = _to_float(_first_valid(row, [
            "stellar_radius", "radius_rsun", "stellar_radius_rsun",
            "radius", "Radius", "Rstar", "rstar", "star_radius", "st_rad"
        ]))
        mass_raw = _to_float(_first_valid(row, [
            "stellar_mass", "mass_msun", "stellar_mass_msun",
            "mass", "Mass", "Mstar", "mstar", "star_mass", "st_mass"
        ]))
        tmag = _to_float(_first_valid(row, [
            "stellar_tmag", "tmag", "Tmag", "TMAG",
            "tessmag", "TESSMAG", "star_tmag", "st_tmag"
        ]))
        nsec = _extract_sector_count(row)

        lum = estimate_luminosity_lsun(radius, teff)
        mass = estimate_mass_msun(
            mass_msun=mass_raw,
            radius_rsun=radius,
            teff_k=teff,
            lum_lsun=lum,
        )
        hz_a = hz_center_au(lum)
        hz_p = orbital_period_days(hz_a, mass)

        theme, score, reason = classify_theme(
            teff=teff,
            radius=radius,
            mass=mass,
            tmag=tmag,
            lum=lum,
            hz_a=hz_a,
            hz_period_days=hz_p,
            nsec=nsec,
            theme_mode=args.theme,
        )

        out = row.to_dict()
        out.update({
            "exotic_target_theme": theme,
            "exotic_target_score": round(float(score), 4),
            "exotic_target_reason": reason,
            "estimated_luminosity_lsun": lum,
            "estimated_mass_msun": mass,
            "hz_center_au": hz_a,
            "hz_center_period_days": hz_p,
            "sector_count_resolved": nsec,
        })
        rows.append(out)

    out_df = pd.DataFrame(rows)
    out_df = out_df.sort_values("exotic_target_score", ascending=False).reset_index(drop=True)

    if args.max_targets > 0:
        out_df = out_df.head(args.max_targets).copy()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() == ".parquet":
        out_df.to_parquet(output_path, index=False)
    else:
        out_df.to_csv(output_path, index=False)

    logger.info(f"Çıktı yazıldı: {output_path}")

    print()
    print("=" * 110)
    print("EXOTIC TARGET POOL SUMMARY")
    print("=" * 110)

    preview_cols = []
    for c in [
        "source_id", "tid", "sector_count_resolved",
        "st_tmag", "st_teff", "st_rad",
        "estimated_mass_msun", "hz_center_period_days",
        "exotic_target_theme", "exotic_target_score"
    ]:
        if c in out_df.columns or c in ["estimated_mass_msun", "hz_center_period_days", "exotic_target_theme", "exotic_target_score", "sector_count_resolved"]:
            preview_cols.append(c)

    print(out_df[preview_cols].head(20).to_string(index=False))
    print("=" * 110)
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
