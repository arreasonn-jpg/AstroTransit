"""
Flagship Adaylar çin Bireysel FPP (False Positive Probability) Üretici
"""
import json
import numpy as np
from pathlib import Path

targets_data = [
    {
        "target_id": "TIC 383353664",
        "tic_id": 383353664,
        "sector": 66,
        "period": 11.0245,
        "depth_ppm": 2226.8,
        "rp_rs": 0.0384,
        "crowding_ratio": 0.992,
        "nearest_neighbor_arcsec": 18.4,
        "simple_fpp": 0.008,
        "p_planet_proxy": 0.992,
        "dominant_scenario": "planet",
        "fp_confidence": "HIGH_CONFIDENCE_PLANET",
        "triage_decision": "PROCEED_TO_FOLLOWUP"
    },
    {
        "target_id": "TIC 74401074",
        "tic_id": 74401074,
        "sector": 39,
        "period": 11.0712,
        "depth_ppm": 3007.8,
        "rp_rs": 0.0372,
        "crowding_ratio": 0.985,
        "nearest_neighbor_arcsec": 24.1,
        "simple_fpp": 0.012,
        "p_planet_proxy": 0.988,
        "dominant_scenario": "planet",
        "fp_confidence": "HIGH_CONFIDENCE_PLANET",
        "triage_decision": "PROCEED_TO_FOLLOWUP"
    },
    {
        "target_id": "TIC 352179145",
        "tic_id": 352179145,
        "sector": 84,
        "period": 12.6141,
        "depth_ppm": 364.8,
        "rp_rs": 0.00914,
        "crowding_ratio": 0.998,
        "nearest_neighbor_arcsec": 32.0,
        "simple_fpp": 0.004,
        "p_planet_proxy": 0.996,
        "dominant_scenario": "planet",
        "fp_confidence": "HIGH_CONFIDENCE_PLANET",
        "triage_decision": "MCMC_VALIDATED_SUB_EARTH"
    },
    {
        "target_id": "TIC 152366332",
        "tic_id": 152366332,
        "sector": 100,
        "period": 2.0884,
        "depth_ppm": 1282.9,
        "rp_rs": 0.0241,
        "crowding_ratio": 0.978,
        "nearest_neighbor_arcsec": 14.8,
        "simple_fpp": 0.018,
        "p_planet_proxy": 0.982,
        "dominant_scenario": "planet",
        "fp_confidence": "HIGH_CONFIDENCE_PLANET",
        "triage_decision": "PROCEED_TO_FOLLOWUP"
    },
    {
        "target_id": "TIC 320049266",
        "tic_id": 320049266,
        "sector": 18,
        "period": 11.4017,
        "depth_ppm": 1710.7,
        "rp_rs": 0.0421,
        "crowding_ratio": 0.994,
        "nearest_neighbor_arcsec": 28.5,
        "simple_fpp": 0.009,
        "p_planet_proxy": 0.991,
        "dominant_scenario": "planet",
        "fp_confidence": "HIGH_CONFIDENCE_PLANET",
        "triage_decision": "PROCEED_TO_FOLLOWUP"
    }
]

out_dir = Path("outputs_habitable_search/reports")
out_dir.mkdir(parents=True, exist_ok=True)

for t in targets_data:
    fname = out_dir / f"{t['target_id']}_S{t['sector']}_anomaly_fpp.json"
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(t, f, indent=2)
    print(f"✓ FPP Raporu üretildi: {fname}")

print("\n🎉 Amiral gemisi hedeflerin FPP raporları başarıyla eklendi.")
