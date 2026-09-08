#!/usr/bin/env python3
"""
Transit architecture anomaly refinement.

Amaç
----
Standart discovery çıktıları içinden:
- period mismatch
- timing anomaly
- transit shape anomaly
- false-positive gibi görünse de mimari olarak ilginç sistemler

ayıklamak.

Önemli not
----------
Bu script false positive elemek için değil,
"review-worthy anomalous architectures" bulmak için tasarlanmıştır.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

from astrotransit.quality.architecture_anomalies import ArchitectureAnomalyScorer


def safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        x = float(x)
        if not np.isfinite(x):
            return default
        return x
    except Exception:
        return default


def compute_period_mismatch_score(row: pd.Series) -> float:
    """
    BLS/TLS/cascade uyumsuzluğundan architecture-interest skoru üret.
    """
    cascade_status = str(row.get("cascade_status", "")).lower()
    bls_p = safe_float(row.get("bls_period"), 0.0)
    tls_p = safe_float(row.get("tls_period"), 0.0)
    adopted_p = safe_float(row.get("period"), 0.0)

    if cascade_status == "period_mismatch":
        base = 55.0
    else:
        base = 0.0

    if bls_p > 0 and tls_p > 0:
        ratio = max(bls_p, tls_p) / max(min(bls_p, tls_p), 1e-6)

        # harmonik / alias yapılar ilginç olabilir
        if 1.8 <= ratio <= 2.2:
            base += 20.0
        elif 2.8 <= ratio <= 3.2:
            base += 18.0
        elif ratio >= 1.2:
            base += 10.0

    if adopted_p > 0 and tls_p > 0:
        ratio2 = max(adopted_p, tls_p) / max(min(adopted_p, tls_p), 1e-6)
        if ratio2 >= 1.15:
            base += 8.0

    return float(np.clip(base, 0.0, 100.0))


def compute_candidate_quality_modifier(row: pd.Series) -> float:
    """
    Çok saçma false positive'ları biraz aşağı çeker, ama tamamen silmez.
    """
    candidate_class = str(row.get("candidate_class", "")).upper()
    rp = safe_float(row.get("planet_radius_rearth"), 0.0)
    period = safe_float(row.get("period"), 0.0)
    snr = safe_float(row.get("snr_adopted"), 0.0)

    mod = 0.0

    if candidate_class == "A":
        mod += 10.0
    elif candidate_class == "C":
        mod += 2.0
    elif candidate_class == "X":
        mod -= 25.0

    if rp > 20:
        mod -= 40.0
    elif rp > 8:
        mod -= 10.0

    if period <= 0:
        mod -= 30.0

    if snr >= 10:
        mod += 8.0
    elif snr >= 6:
        mod += 4.0

    return float(mod)


def classify_architecture_bucket(score: float) -> str:
    if score >= 75:
        return "TIER_A_ARCHITECTURE"
    if score >= 58:
        return "TIER_B_REVIEW"
    if score >= 42:
        return "TIER_C_MAYBE_INTERESTING"
    return "LOW_PRIORITY"


def architecture_reason(
    row: pd.Series,
    arch_score: float,
    period_mismatch_score: float,
    model_score: float,
) -> str:
    bits = []

    cascade_status = str(row.get("cascade_status", "")).lower()
    timing_rms = safe_float(row.get("timing_rms_min"), 0.0)
    symmetry = safe_float(row.get("transit_symmetry"), 1.0)
    odd_even = safe_float(row.get("tls_odd_even_mismatch"), 0.0)

    if cascade_status == "period_mismatch":
        bits.append("period-mismatch")
    if period_mismatch_score >= 60:
        bits.append("strong-period-structure")
    if model_score >= 20:
        bits.append("timing/shape-anomaly")
    if timing_rms >= 10:
        bits.append(f"timing-rms={timing_rms:.1f}min")
    if symmetry < 0.97:
        bits.append(f"symmetry={symmetry:.3f}")
    if odd_even >= 0.8:
        bits.append(f"odd-even={odd_even:.2f}")

    if not bits:
        bits.append("weak-architecture-signal")

    return "; ".join(bits)


def main():
    parser = argparse.ArgumentParser(description="Refine architecture anomalies")
    parser.add_argument(
        "--input",
        type=str,
        default="outputs_discovery/parquet/astrotransit_candidates.parquet",
    )
    parser.add_argument(
        "--output-prefix",
        type=str,
        default="outputs_discovery/novel_candidates_architecture_prioritized",
    )
    parser.add_argument(
        "--include-confirmed",
        action="store_true",
        help="Include confirmed candidates too (default: yes in current implementation).",
    )
    args = parser.parse_args()

    inpath = Path(args.input)
    if not inpath.exists():
        raise FileNotFoundError(f"Input not found: {inpath}")

    df = pd.read_parquet(inpath)
    logger.info(f"Girdi yüklendi: {inpath} | satır={len(df)}")

    scorer = ArchitectureAnomalyScorer()
    rows = []

    for _, row in df.iterrows():
        _source_id = row.get("source_id", "")
        _period = safe_float(row.get("period"), 0.0)
        _candidate_class = str(row.get("candidate_class", "")).upper()

        # tamamen bozuk candidate'ları tut ama ağır ceza ver
        timing_rms_min = safe_float(row.get("timing_rms_min"), 0.0)
        transit_symmetry = safe_float(row.get("transit_symmetry"), 1.0)
        residual_rms_ppm = safe_float(row.get("residual_rms_ppm"), 0.0)
        odd_even = safe_float(row.get("tls_odd_even_mismatch"), 0.0)
        n_transits = int(safe_float(row.get("n_transits"), 0.0))

        anomaly_flag = "REVIEW" if bool(row.get("is_anomalous", False)) else "NONE"

        arch = scorer.evaluate(
            timing_rms_min=timing_rms_min,
            transit_symmetry=transit_symmetry,
            ingress_egress_ratio=1.0,  # mevcut tabloda yoksa nötr
            odd_even_mismatch=odd_even,
            residual_rms_ppm=residual_rms_ppm,
            anomaly_flag=anomaly_flag,
            pre_post_dip_score=0.0,
            shoulder_score=0.0,
            folded_multipeak_score=0.0,
            trojan_signal_score=0.0,
            exomoon_signal_score=0.0,
            lagrange_stationkeeping_review_score=None,
            n_transits=n_transits,
        )

        period_mismatch_score = compute_period_mismatch_score(row)
        quality_mod = compute_candidate_quality_modifier(row)

        final_score = (
            0.55 * arch.architecture_anomaly_score +
            0.45 * period_mismatch_score +
            quality_mod
        )
        final_score = float(np.clip(final_score, 0.0, 100.0))

        bucket = classify_architecture_bucket(final_score)
        reason = architecture_reason(
            row=row,
            arch_score=final_score,
            period_mismatch_score=period_mismatch_score,
            model_score=arch.architecture_anomaly_score,
        )

        out = row.to_dict()
        out.update({
            "architecture_anomaly_score": round(float(arch.architecture_anomaly_score), 4),
            "architecture_flag": arch.architecture_flag,
            "architecture_summary_label": arch.summary_label,
            "period_mismatch_score": round(float(period_mismatch_score), 4),
            "candidate_quality_modifier": round(float(quality_mod), 4),
            "architecture_interest_score": round(float(final_score), 4),
            "architecture_priority_bucket": bucket,
            "architecture_priority_reason": reason,
        })
        rows.append(out)

    out_df = pd.DataFrame(rows)
    out_df = out_df.sort_values(
        ["architecture_interest_score", "snr_adopted"],
        ascending=[False, False],
    ).reset_index(drop=True)

    prefix = Path(args.output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    parquet_path = prefix.with_suffix(".parquet")
    csv_path = prefix.with_suffix(".csv")

    out_df.to_parquet(parquet_path, index=False)
    out_df.to_csv(csv_path, index=False)

    logger.info(f"Parquet yazıldı: {parquet_path}")
    logger.info(f"CSV yazıldı: {csv_path}")

    print()
    print("=" * 120)
    print("ARCHITECTURE ANOMALY SUMMARY")
    print("=" * 120)
    preview_cols = [
        c for c in [
            "source_id", "sector", "cascade_status", "candidate_class",
            "period", "planet_radius_rearth", "snr_adopted",
            "architecture_anomaly_score", "period_mismatch_score",
            "architecture_interest_score", "architecture_priority_bucket",
            "architecture_priority_reason"
        ] if c in out_df.columns
    ]
    print(out_df[preview_cols].head(25).to_string(index=False))
    print("=" * 120)
    print(f"Output: {parquet_path}")
    print(f"Output: {csv_path}")


if __name__ == "__main__":
    main()
