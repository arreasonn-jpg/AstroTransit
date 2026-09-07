#!/usr/bin/env python3
"""
Yeni bilim hedeflerine göre aday önceliklendirme script'i.

Temalar
-------
- EARTHLIKE_TEMPERATE
- TEMPERATE_SMALL_WORLD
- POTENTIAL_MOON_HOST
- ARCHITECTURE_ANOMALY
- UNSTABLE_COORBITAL_REVIEW
- STANDARD_TRANSIT

Girdi
-----
Varsayılan olarak:
    outputs_discovery/novel_candidates_science_prioritized.parquet
veya fallback:
    outputs_discovery/novel_candidates_prioritized.parquet

Çıktı
-----
- outputs_discovery/novel_candidates_exotic_prioritized.parquet
- outputs_discovery/novel_candidates_exotic_prioritized.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from astrotransit.quality.habitability import HabitabilityScorer
from astrotransit.quality.moon_potential import MoonHostScorer
from astrotransit.quality.architecture_anomalies import ArchitectureAnomalyScorer


def _first_valid(row: pd.Series, names: list[str], default=None):
    for name in names:
        if name in row.index:
            val = row[name]
            if pd.notna(val):
                return val
    return default


def _to_float(x, default=None):
    try:
        if x is None or (isinstance(x, float) and not np.isfinite(x)):
            return default
        return float(x)
    except Exception:
        return default


def _theme_and_bucket(
    earthlike_score: float,
    hz_score: float,
    moon_host_score: float,
    architecture_score: float,
    lagrange_score: float,
    crowding_ratio: float | None,
    anomaly_flag: str | None,
    simple_fpp: float | None,
) -> tuple[str, float, str, str]:
    """
    science_theme, science_interest_score, exotic_priority_bucket, reason
    """

    crowding = 1.0 if crowding_ratio is None else float(crowding_ratio)
    fpp = 0.0 if simple_fpp is None else float(simple_fpp)
    af = "" if anomaly_flag is None else str(anomaly_flag).upper()

    # Tema seçimi
    if lagrange_score >= 70:
        theme = "UNSTABLE_COORBITAL_REVIEW"
        raw = 0.70 * lagrange_score + 0.30 * architecture_score
        reason = "Persistent/co-orbital architectural anomaly merits unstable-region review."
    elif earthlike_score >= 72 and hz_score >= 55:
        theme = "EARTHLIKE_TEMPERATE"
        raw = 0.75 * earthlike_score + 0.25 * hz_score
        reason = "Radius and temperate/HZ proxies are consistent with an Earthlike small-world priority."
    elif earthlike_score >= 52 and hz_score >= 45:
        theme = "TEMPERATE_SMALL_WORLD"
        raw = 0.70 * earthlike_score + 0.30 * hz_score
        reason = "Small-world candidate near the temperate/HZ regime."
    elif moon_host_score >= 65:
        theme = "POTENTIAL_MOON_HOST"
        raw = 0.85 * moon_host_score + 0.15 * architecture_score
        reason = "Large/HZ-adjacent world with favorable moon-host geometry."
    elif architecture_score >= 50:
        theme = "ARCHITECTURE_ANOMALY"
        raw = architecture_score
        reason = "Transit morphology/timing suggests an unusual system architecture."
    else:
        theme = "STANDARD_TRANSIT"
        raw = max(earthlike_score, moon_host_score, architecture_score) * 0.75
        reason = "Scientifically valid candidate, but not strongly prioritized under the new exotic themes."

    # Cezalar / bonuslar
    interest = float(raw)

    if crowding < 0.75:
        interest -= 20.0
        reason += " Heavy crowding penalty."
    elif crowding < 0.90:
        interest -= 8.0
        reason += " Moderate crowding penalty."

    if fpp > 0.70:
        interest -= 18.0
        reason += " High proxy FP penalty."
    elif fpp > 0.40:
        interest -= 8.0
        reason += " Moderate proxy FP penalty."

    if af == "REJECT":
        interest -= 15.0
        reason += " Anomaly reject penalty."
    elif af == "REVIEW":
        interest -= 6.0
        reason += " Anomaly review penalty."

    interest = float(np.clip(interest, 0.0, 100.0))

    # Bucket
    if theme == "UNSTABLE_COORBITAL_REVIEW" and interest >= 55:
        bucket = "TIER_A_EXOTIC"
    elif theme in {"EARTHLIKE_TEMPERATE", "POTENTIAL_MOON_HOST"} and interest >= 65:
        bucket = "TIER_A_EXOTIC"
    elif theme in {"TEMPERATE_SMALL_WORLD", "ARCHITECTURE_ANOMALY"} and interest >= 55:
        bucket = "TIER_B_STRONG"
    elif interest >= 40:
        bucket = "TIER_C_REVIEW"
    else:
        bucket = "LOW_PRIORITY"

    return theme, interest, bucket, reason


def main():
    parser = argparse.ArgumentParser(description="Refine exotic priorities")
    parser.add_argument(
        "--input",
        type=str,
        default="outputs_discovery/novel_candidates_science_prioritized.parquet",
        help="Input parquet/csv file",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="outputs_discovery/novel_candidates_exotic_prioritized",
        help="Output file prefix (without extension)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        fallback = Path("outputs_discovery/novel_candidates_prioritized.parquet")
        if fallback.exists():
            logger.warning(f"{input_path} bulunamadı; fallback kullanılacak: {fallback}")
            input_path = fallback
        else:
            raise FileNotFoundError(f"Girdi dosyası bulunamadı: {args.input}")

    if input_path.suffix.lower() == ".csv":
        df = pd.read_csv(input_path)
    else:
        df = pd.read_parquet(input_path)

    logger.info(f"Girdi yüklendi: {input_path} | satır={len(df)}")

    habit = HabitabilityScorer()
    moon = MoonHostScorer()
    arch = ArchitectureAnomalyScorer()

    out_rows = []
    for _, row in df.iterrows():
        planet_radius_rearth = _to_float(_first_valid(row, [
            "planet_radius_rearth", "rp_rearth", "planet_radius", "radius_rearth"
        ]))
        equilibrium_temperature_k = _to_float(_first_valid(row, [
            "equilibrium_temperature_k", "teq_k", "equilibrium_temperature"
        ]))
        insolation_flux = _to_float(_first_valid(row, [
            "insolation_flux", "insolation_flux_searth", "s_earth", "stellar_flux"
        ]))
        semi_major_axis_au = _to_float(_first_valid(row, [
            "semi_major_axis_au", "a_au", "sma_au"
        ]))
        stellar_radius_rsun = _to_float(_first_valid(row, [
            "stellar_radius", "radius_rsun", "stellar_radius_rsun"
        ]))
        stellar_teff_k = _to_float(_first_valid(row, [
            "stellar_teff", "teff_k", "stellar_teff_k", "teff"
        ]))
        stellar_mass_msun = _to_float(_first_valid(row, [
            "stellar_mass", "mass_msun", "stellar_mass_msun"
        ]))
        crowding_ratio = _to_float(_first_valid(row, [
            "crowding_ratio", "crowdsap"
        ]))
        anomaly_flag = _first_valid(row, [
            "anomaly_flag", "science_anomaly_flag"
        ])
        simple_fpp = _to_float(_first_valid(row, [
            "simple_fpp", "fpp_proxy", "fpp"
        ]))
        transit_symmetry = _to_float(_first_valid(row, [
            "transit_symmetry"
        ]))
        ingress_egress_ratio = _to_float(_first_valid(row, [
            "ingress_egress_ratio"
        ]))
        timing_rms_min = _to_float(_first_valid(row, [
            "timing_rms_min"
        ]))
        odd_even_mismatch = _to_float(_first_valid(row, [
            "odd_even_mismatch", "tls_odd_even_mismatch"
        ]))
        residual_rms_ppm = _to_float(_first_valid(row, [
            "residual_rms_ppm"
        ]))
        n_transits = _to_float(_first_valid(row, [
            "n_transits"
        ]))

        # Gelecekte discovery/anomaly katmanı bu alanları doldurursa otomatik kullanılır
        pre_post_dip_score = _to_float(_first_valid(row, [
            "pre_post_dip_score", "prepost_dip_score"
        ]), default=0.0)
        shoulder_score = _to_float(_first_valid(row, [
            "shoulder_score"
        ]), default=0.0)
        folded_multipeak_score = _to_float(_first_valid(row, [
            "folded_multipeak_score", "multipeak_score"
        ]), default=0.0)
        trojan_signal_score = _to_float(_first_valid(row, [
            "trojan_signal_score", "coorbital_signal_score"
        ]), default=0.0)
        exomoon_signal_score = _to_float(_first_valid(row, [
            "exomoon_signal_score", "moon_signal_score"
        ]), default=0.0)
        lagrange_score_in = _to_float(_first_valid(row, [
            "lagrange_stationkeeping_review_score",
            "unstable_coorbital_score",
        ]), default=None)

        h = habit.evaluate(
            planet_radius_rearth=planet_radius_rearth,
            equilibrium_temperature_k=equilibrium_temperature_k,
            insolation_flux=insolation_flux,
            semi_major_axis_au=semi_major_axis_au,
            stellar_radius_rsun=stellar_radius_rsun,
            stellar_teff_k=stellar_teff_k,
        )

        m = moon.evaluate(
            planet_radius_rearth=planet_radius_rearth,
            stellar_mass_msun=stellar_mass_msun,
            semi_major_axis_au=semi_major_axis_au,
            equilibrium_temperature_k=equilibrium_temperature_k,
            insolation_flux=insolation_flux,
            crowding_ratio=crowding_ratio,
        )

        a = arch.evaluate(
            timing_rms_min=timing_rms_min,
            transit_symmetry=transit_symmetry,
            ingress_egress_ratio=ingress_egress_ratio,
            odd_even_mismatch=odd_even_mismatch,
            residual_rms_ppm=residual_rms_ppm,
            anomaly_flag=anomaly_flag,
            pre_post_dip_score=pre_post_dip_score,
            shoulder_score=shoulder_score,
            folded_multipeak_score=folded_multipeak_score,
            trojan_signal_score=trojan_signal_score,
            exomoon_signal_score=exomoon_signal_score,
            lagrange_stationkeeping_review_score=lagrange_score_in,
            n_transits=int(n_transits) if n_transits is not None else None,
        )

        theme, interest, bucket, reason = _theme_and_bucket(
            earthlike_score=h.earth_similarity_score,
            hz_score=h.hz_score,
            moon_host_score=m.moon_host_score,
            architecture_score=a.architecture_anomaly_score,
            lagrange_score=a.lagrange_stationkeeping_review_score,
            crowding_ratio=crowding_ratio,
            anomaly_flag=anomaly_flag,
            simple_fpp=simple_fpp,
        )

        out = row.to_dict()
        out.update({
            "hz_score": round(float(h.hz_score), 4),
            "temperate_score": round(float(h.temperate_score), 4),
            "earth_similarity_score": round(float(h.earth_similarity_score), 4),
            "hz_zone": h.hz_zone,
            "temperate_flag": h.temperate_flag,
            "earthlike_flag": h.earthlike_flag,
            "habitability_summary_label": h.summary_label,
            "stellar_luminosity_lsun": h.stellar_luminosity_lsun,
            "insolation_s_earth": h.insolation_s_earth,

            "moon_host_score": round(float(m.moon_host_score), 4),
            "moon_host_flag": m.moon_host_flag,
            "moon_host_summary_label": m.summary_label,
            "estimated_planet_mass_mearth": m.estimated_planet_mass_mearth,
            "hill_radius_au": m.hill_radius_au,
            "stable_prograde_zone_au": m.stable_prograde_zone_au,
            "stable_prograde_zone_planet_radii": m.stable_prograde_zone_planet_radii,

            "architecture_anomaly_score": round(float(a.architecture_anomaly_score), 4),
            "architecture_flag": a.architecture_flag,
            "architecture_summary_label": a.summary_label,
            "ttv_score": round(float(a.ttv_score), 4),
            "asymmetry_score": round(float(a.asymmetry_score), 4),
            "residual_structure_score": round(float(a.residual_structure_score), 4),
            "pre_post_dip_score_out": round(float(a.pre_post_dip_score), 4),
            "shoulder_score_out": round(float(a.shoulder_score), 4),
            "folded_multipeak_score_out": round(float(a.folded_multipeak_score), 4),
            "trojan_signal_score_out": round(float(a.trojan_signal_score), 4),
            "exomoon_signal_score_out": round(float(a.exomoon_signal_score), 4),
            "lagrange_stationkeeping_review_score": round(float(a.lagrange_stationkeeping_review_score), 4),

            "science_theme": theme,
            "science_interest_score": round(float(interest), 4),
            "exotic_priority_bucket": bucket,
            "exotic_priority_reason": reason,
        })
        out_rows.append(out)

    out_df = pd.DataFrame(out_rows)

    # sıralama
    sort_cols = ["science_interest_score"]
    ascending = [False]
    if "p_planet_proxy" in out_df.columns:
        sort_cols.append("p_planet_proxy")
        ascending.append(False)
    out_df = out_df.sort_values(sort_cols, ascending=ascending).reset_index(drop=True)

    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    parquet_path = prefix.with_suffix(".parquet")
    csv_path = prefix.with_suffix(".csv")

    out_df.to_parquet(parquet_path, index=False)
    out_df.to_csv(csv_path, index=False)

    logger.info(f"Parquet yazıldı: {parquet_path}")
    logger.info(f"CSV yazıldı: {csv_path}")

    print()
    print("=" * 110)
    print("EXOTIC PRIORITY SUMMARY")
    print("=" * 110)
    cols = [
        "target_id", "sector", "science_theme", "science_interest_score",
        "exotic_priority_bucket", "earth_similarity_score",
        "moon_host_score", "architecture_anomaly_score"
    ]
    preview = out_df[[c for c in cols if c in out_df.columns]].head(20)
    print(preview.to_string(index=False))
    print("=" * 110)
    print(f"Output: {parquet_path}")
    print(f"Output: {csv_path}")


if __name__ == "__main__":
    main()
