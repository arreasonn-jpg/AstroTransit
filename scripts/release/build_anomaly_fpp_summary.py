#!/usr/bin/env python3
"""
Anomaly + FPP sonuçlarını tek bir özet tabloda toplar.

Kullanım:
    python scripts/release/build_anomaly_fpp_summary.py

    # veya özel klasör:
    python scripts/release/build_anomaly_fpp_summary.py \
        --input-dir outputs_anomaly_fpp \
        --output-dir outputs_anomaly_fpp/summary
"""

from __future__ import annotations

import argparse
import json
import csv
from pathlib import Path
from datetime import datetime, timezone

from loguru import logger


# ──────────────────────────────────────────────────────────────
# Triage kuralları
# ──────────────────────────────────────────────────────────────

def compute_triage_decision(row: dict) -> tuple[str, str]:
    """
    Anomaly + FPP + CROWDSAP bilgilerine göre
    triage kararı ve risk notu üretir.

    Returns
    -------
    (triage_decision, risk_note)
    """

    fpp = float(row.get("simple_fpp", 0.0))
    anomaly_flag = row.get("anomaly_flag", "UNKNOWN")
    crowdsap = row.get("crowding_ratio")
    delta_mag = row.get("brightest_neighbor_delta_mag")
    nearest = row.get("nearest_neighbor_arcsec")
    p_neb = float(row.get("p_neb", 0.0))
    p_eb = float(row.get("p_eb", 0.0))
    p_beb = float(row.get("p_beb", 0.0))
    dominant = row.get("dominant_scenario", "none")
    n_neighbors = row.get("gaia_neighbors_within_60arcsec")

    notes = []

    # ── CROWDSAP ciddi kontaminasyon ──
    if crowdsap is not None and float(crowdsap) < 0.60:
        notes.append(f"CRITICAL_CROWDSAP({crowdsap:.3f})")
        return "DEPRIORITIZED_CONTAMINATION_RISK", "; ".join(notes)

    # ── Ambiguous host: yakın + parlak komşu ──
    if (
        delta_mag is not None
        and nearest is not None
        and float(delta_mag) > -3.0
        and float(nearest) < 10.0
        and crowdsap is not None
        and float(crowdsap) < 0.90
    ):
        notes.append(f"HOST_AMBIGUITY(nearest={nearest:.1f}\",dmag={delta_mag:.2f},CROWDSAP={crowdsap:.3f})")
        return "FOLLOWUP_WITH_HOST_AMBIGUITY_WARNING", "; ".join(notes)

    # ── Anomaly CLEAN + düşük FPP ──
    if anomaly_flag == "CLEAN" and fpp < 0.20:
        notes.append("CLEAN_PROFILE")
        return "TOP_CLEAN_FOLLOWUP", "; ".join(notes)

    # ── Anomaly CLEAN + orta FPP ──
    if anomaly_flag == "CLEAN" and fpp < 0.50:
        if dominant == "eb":
            notes.append(f"EB_PROXY_ELEVATED(p_eb={p_eb:.2f})")
        if dominant == "neb":
            notes.append(f"NEB_PROXY_ELEVATED(p_neb={p_neb:.2f})")
        if dominant == "beb":
            notes.append(f"BEB_PROXY_ELEVATED(p_beb={p_beb:.2f})")
        return "FOLLOWUP_WITH_CAUTION", "; ".join(notes) if notes else "moderate_fpp"

    # ── Anomaly CLEAN + yüksek FPP ──
    if anomaly_flag == "CLEAN" and fpp >= 0.50:
        if p_neb >= 0.50:
            notes.append(f"HIGH_NEB_DESPITE_CLEAN_ANOMALY(p_neb={p_neb:.2f})")
        if p_beb >= 0.20:
            notes.append(f"BEB_CONCERN(p_beb={p_beb:.2f},CROWDSAP={crowdsap})")
        return "FOLLOWUP_WITH_HOST_AMBIGUITY_WARNING", "; ".join(notes) if notes else "high_fpp_anomaly_clean"

    # ── Anomaly REVIEW ──
    if anomaly_flag == "REVIEW":
        if fpp < 0.50:
            notes.append("ANOMALY_REVIEW_MODERATE_FPP")
            return "KEEP_WITH_CROWDING_CAUTION", "; ".join(notes)
        else:
            notes.append(f"ANOMALY_REVIEW_HIGH_FPP(fpp={fpp:.2f})")
            return "MANUAL_REVIEW_REQUIRED", "; ".join(notes)

    # ── Anomaly REJECT ──
    if anomaly_flag == "REJECT":
        if fpp < 0.35:
            notes.append("ANOMALY_REJECT_BUT_LOW_FPP")
            return "SHAPE_REVIEW_REQUIRED", "; ".join(notes)
        else:
            notes.append(f"ANOMALY_REJECT_HIGH_FPP(fpp={fpp:.2f})")
            return "DEPRIORITIZED_MULTIPLE_FLAGS", "; ".join(notes)

    # ── Fallback ──
    return "MANUAL_REVIEW_REQUIRED", "unclassified"


# ──────────────────────────────────────────────────────────────
# JSON okuma
# ──────────────────────────────────────────────────────────────

def parse_anomaly_fpp_json(path: Path) -> dict | None:
    """Tek bir anomaly+fpp JSON dosyasını okur ve düz sözlüğe çevirir."""

    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as exc:
        logger.warning(f"JSON okunamadı: {path} — {exc}")
        return None

    target_id = d.get("target_id", "")
    tic_id = d.get("tic_id", 0)
    sector = d.get("sector", -1)
    params = d.get("parameters", {})
    spoc = d.get("spoc_metadata", {})
    gaia = d.get("gaia_neighbors", {})
    anomaly = d.get("anomaly", {})
    fpp = d.get("fpp", {})

    combined = anomaly.get("combined", {})
    residual = anomaly.get("residual", {})
    transit_c = anomaly.get("transit_consistency", {})
    timing = anomaly.get("timing", {})

    row = {
        "target_id": target_id,
        "tic_id": tic_id,
        "sector": sector,
        "period": params.get("period"),
        "t0": params.get("t0"),
        "duration": params.get("duration"),
        "depth": params.get("depth"),
        "rp_rs": params.get("rp_rs"),

        # SPOC
        "crowding_ratio": spoc.get("crowding_ratio"),
        "centroid_shift_arcsec": spoc.get("centroid_shift_arcsec"),
        "tmag": spoc.get("tmag"),

        # Gaia
        "gaia_neighbors_within_60arcsec": gaia.get("gaia_neighbors_within_60arcsec"),
        "nearest_neighbor_arcsec": gaia.get("nearest_neighbor_arcsec"),
        "brightest_neighbor_delta_mag": gaia.get("brightest_neighbor_delta_mag"),
        "target_gaia_mag": gaia.get("target_gaia_mag"),
        "gaia_self_sep_arcsec": gaia.get("target_sep_arcsec"),
        "gaia_self_method": gaia.get("self_selection_method"),

        # Anomaly
        "residual_flag": residual.get("flag", ""),
        "residual_score": residual.get("score", 0.0),
        "transit_consistency_flag": transit_c.get("flag", ""),
        "transit_consistency_score": transit_c.get("score", 0.0),
        "timing_flag": timing.get("flag", ""),
        "timing_score": timing.get("score", 0.0),
        "anomaly_flag": combined.get("anomaly_flag", ""),
        "anomaly_score": combined.get("anomaly_score", 0.0),
        "anomaly_action": combined.get("recommended_action", ""),

        # FPP
        "p_eb": fpp.get("p_eb", 0.0),
        "p_beb": fpp.get("p_beb", 0.0),
        "p_neb": fpp.get("p_neb", 0.0),
        "simple_fpp": fpp.get("fpp", 0.0),
        "p_planet_proxy": fpp.get("p_planet", 1.0),
        "dominant_scenario": fpp.get("dominant_scenario", ""),
        "fp_confidence": fpp.get("confidence", ""),
        "fp_action": fpp.get("recommended_action", ""),

        # Source JSON
        "source_json": str(path),
    }

    return row


# ──────────────────────────────────────────────────────────────
# Ana akış
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Anomaly + FPP sonuçlarını tek tabloda topla"
    )
    parser.add_argument(
        "--input-dir", type=str, default="outputs_anomaly_fpp",
        help="Anomaly+FPP JSON dosyalarının klasörü",
    )
    parser.add_argument(
        "--output-dir", type=str, default="outputs_anomaly_fpp/summary",
        help="Çıktı klasörü",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(input_dir.glob("TIC_*_anomaly_fpp.json"))
    logger.info(f"{len(json_files)} anomaly+fpp JSON dosyası bulundu.")

    if not json_files:
        logger.warning("Hiç dosya bulunamadı.")
        return

    rows = []
    for jf in json_files:
        row = parse_anomaly_fpp_json(jf)
        if row is not None:
            triage_decision, risk_note = compute_triage_decision(row)
            row["triage_decision"] = triage_decision
            row["risk_note"] = risk_note
            rows.append(row)
            logger.info(
                f"{row['target_id']} S{row['sector']} → "
                f"triage={triage_decision}"
            )

    # Sırala: p_planet_proxy azalan
    rows.sort(key=lambda r: float(r.get("p_planet_proxy", 0.0)), reverse=True)

    # ── CSV yaz ──
    csv_columns = [
        "target_id", "tic_id", "sector",
        "anomaly_flag", "anomaly_score",
        "residual_flag", "transit_consistency_flag", "timing_flag",
        "simple_fpp", "p_planet_proxy",
        "p_eb", "p_beb", "p_neb", "dominant_scenario", "fp_confidence",
        "crowding_ratio", "gaia_neighbors_within_60arcsec",
        "nearest_neighbor_arcsec", "brightest_neighbor_delta_mag",
        "target_gaia_mag", "gaia_self_sep_arcsec", "gaia_self_method",
        "triage_decision", "risk_note",
        "period", "depth", "rp_rs", "tmag",
    ]

    csv_path = output_dir / "anomaly_fpp_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    logger.info(f"CSV yazıldı: {csv_path}")

    # ── JSON yaz ──
    json_path = output_dir / "anomaly_fpp_summary.json"
    summary = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "n_candidates": len(rows),
        "candidates": rows,
    }
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"JSON yazıldı: {json_path}")

    # ── Ekran özeti ──
    print()
    print("=" * 100)
    print("ANOMALY + FPP SUMMARY")
    print("=" * 100)
    print(f"{'TIC':<14} {'S':>3} {'Anomaly':<10} {'Score':>6} {'FPP':>6} {'Ppl':>6} {'Dom':>5} {'CROWD':>6} {'Near\"':>7} {'Δmag':>7} {'Triage':<40}")
    print("-" * 100)
    for r in rows:
        print(
            f"{r['target_id']:<14} "
            f"{r['sector']:>3} "
            f"{r['anomaly_flag']:<10} "
            f"{float(r.get('anomaly_score',0)):>6.3f} "
            f"{float(r.get('simple_fpp',0)):>6.3f} "
            f"{float(r.get('p_planet_proxy',0)):>6.3f} "
            f"{str(r.get('dominant_scenario',''))[:5]:>5} "
            f"{float(r.get('crowding_ratio',0)) if r.get('crowding_ratio') else 0:>6.3f} "
            f"{float(r.get('nearest_neighbor_arcsec',0)) if r.get('nearest_neighbor_arcsec') else 0:>7.2f} "
            f"{float(r.get('brightest_neighbor_delta_mag',0)) if r.get('brightest_neighbor_delta_mag') else 0:>7.2f} "
            f"{r.get('triage_decision',''):<40}"
        )
    print("=" * 100)

    # Triage dağılımı
    from collections import Counter
    triage_counts = Counter(r["triage_decision"] for r in rows)
    print("\nTriage dağılımı:")
    for k, v in triage_counts.most_common():
        print(f"  {k}: {v}")

    print(f"\nÇıktılar: {csv_path}, {json_path}")


if __name__ == "__main__":
    main()
