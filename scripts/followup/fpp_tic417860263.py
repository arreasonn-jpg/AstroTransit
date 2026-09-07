"""
TIC 417860263 / HD 224792
Basitleştirilmiş False Positive Probability (FPP) Hesabı

Yöntem:
    triceratops benzeri senaryo bazlı FPP tahmini.
    Gerçek transit (TP) vs false positive (FP) senaryolarının
    göreceli olasılıklarını hesaplar.

Senaryolar:
    TP  : Gerçek gezegen transiti (hedef yıldızda)
    BEB : Background Eclipsing Binary (arka plan tutulma çifti)
    NEB : Nearby Eclipsing Binary (Gaia komşu kaynaklardan)
    HEB : Hierarchical Eclipsing Binary (hedef yıldıza bağlı yoldaş)
"""

from __future__ import annotations

import json
import math
from pathlib import Path

OUT_DIR = Path("outputs_discovery/reports")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────
# Gözlemsel parametreler
# ─────────────────────────────────────────────
TIC_ID = 417860263
HOST_NAME = "HD 224792"
SECTOR = 57

TRANSIT_DEPTH_PPM = 630.0          # ppm
PERIOD_DAYS = 2.853511
RP_RS = 0.025096
A_OVER_RS = 8.189
CONTAMINATION_RATIO = 0.011693     # ExoFOP TIC v8.2
HOST_GMAG = 6.922

# Gaia komşular (10 arcsec içinde, host hariç)
GAIA_NEIGHBORS = [
    {"source": "429915991429427840", "Gmag": 15.780, "Plx": 0.3452},
    {"source": "429915991430344832", "Gmag": 20.757, "Plx": None},
    {"source": "429915991435698304", "Gmag": 18.497, "Plx": 1.1371},
    {"source": "429915991435731456", "Gmag": 20.149, "Plx": 1.0644},
]

# ─────────────────────────────────────────────
# Yardımcı fonksiyonlar
# ─────────────────────────────────────────────

def flux_ratio(delta_gmag: float) -> float:
    """
    Delta mag'dan akı oranı hesapla.
    f_neighbor / f_host = 10^(-delta_gmag / 2.5)
    """
    return 10 ** (-delta_gmag / 2.5)


def max_eclipse_depth_for_binary(flux_ratio_neighbor: float) -> float:
    """
    Bir komşu kaynak tam tutulma yapsa hedef apertüründe
    görünen maksimum transit derinliği (ppm).
    """
    return flux_ratio_neighbor * 1_000_000.0


def is_depth_consistent(
    observed_depth_ppm: float,
    max_fp_depth_ppm: float,
    tolerance: float = 1.5,
) -> bool:
    """
    FP senaryosunun gözlenen derinliği açıklayıp açıklayamayacağını
    kontrol eder.
    """
    return max_fp_depth_ppm >= (observed_depth_ppm / tolerance)


# ─────────────────────────────────────────────
# Prior olasılıklar
# ─────────────────────────────────────────────
# Giacalone & Dressing (2020) ve genel gezegen occurrence rates
# üzerinden basit önsel değerler.

PRIOR_TP = 0.80    # Gezegen olasılığı (parlak, izole yıldız, makul Rp)
PRIOR_BEB = 0.05   # Arka plan tutulma çifti
PRIOR_NEB = 0.03   # Yakın komşu tutulma çifti
PRIOR_HEB = 0.12   # Hiyerarşik çift yıldız


def normalize(priors: dict) -> dict:
    total = sum(priors.values())
    return {k: v / total for k, v in priors.items()}


# ─────────────────────────────────────────────
# Likelihood modifiers
# ─────────────────────────────────────────────

def compute_neb_likelihood_modifier(
    neighbors: list[dict],
    observed_depth_ppm: float,
) -> float:
    """
    NEB senaryosu için likelihood modifier.

    Hiçbir komşu gözlenen derinliği tek başına açıklayamıyorsa,
    NEB olasılığı baskılanır.
    """
    can_explain = []
    for nb in neighbors:
        delta_g = nb["Gmag"] - HOST_GMAG
        fr = flux_ratio(delta_g)
        max_depth = max_eclipse_depth_for_binary(fr)
        can_explain.append(is_depth_consistent(observed_depth_ppm, max_depth))

    # Hiçbiri açıklayamıyorsa: güçlü baskı
    if not any(can_explain):
        return 0.02
    # Bazıları açıklayabiliyorsa: zayıf baskı
    return 0.3


def compute_beb_likelihood_modifier(
    contamination_ratio: float,
) -> float:
    """
    BEB senaryosu için likelihood modifier.

    Düşük contamination, BEB olasılığını baskılar.
    """
    if contamination_ratio < 0.02:
        return 0.05
    elif contamination_ratio < 0.05:
        return 0.15
    else:
        return 0.4


def compute_heb_likelihood_modifier(rp_rs: float) -> float:
    """
    HEB senaryosu için likelihood modifier.

    rp_rs < 0.1 olduğunda HEB olasılığı daha düşük
    (çünkü çok derin olmayan transit, tam tutulmayı zorlaştırır).
    """
    if rp_rs < 0.05:
        return 0.3
    elif rp_rs < 0.1:
        return 0.5
    else:
        return 0.8


# ─────────────────────────────────────────────
# Ana hesaplama
# ─────────────────────────────────────────────

def compute_fpp():
    print(f"\n{'='*60}")
    print(f"TIC {TIC_ID} / {HOST_NAME} — FPP Hesabı")
    print(f"{'='*60}")

    # Komşu analizi
    print(f"\n[1] Gaia Komşu Analizi (10 arcsec içinde)")
    for nb in GAIA_NEIGHBORS:
        delta_g = nb["Gmag"] - HOST_GMAG
        fr = flux_ratio(delta_g)
        max_depth = max_eclipse_depth_for_binary(fr)
        can = is_depth_consistent(TRANSIT_DEPTH_PPM, max_depth)
        print(
            f"  Gaia {nb['source']}: "
            f"ΔG={delta_g:.1f}, "
            f"flux_ratio={fr:.6f}, "
            f"max_eclipse_depth={max_depth:.1f} ppm, "
            f"can_explain_transit={can}"
        )

    # Likelihood modifiers
    neb_mod = compute_neb_likelihood_modifier(GAIA_NEIGHBORS, TRANSIT_DEPTH_PPM)
    beb_mod = compute_beb_likelihood_modifier(CONTAMINATION_RATIO)
    heb_mod = compute_heb_likelihood_modifier(RP_RS)
    tp_mod = 1.0  # TP için modifier yok

    print(f"\n[2] Likelihood Modifiers")
    print(f"  TP  modifier: {tp_mod:.3f}")
    print(f"  BEB modifier: {beb_mod:.3f} (contamination={CONTAMINATION_RATIO:.4f})")
    print(f"  NEB modifier: {neb_mod:.3f} (komşu analizi bazlı)")
    print(f"  HEB modifier: {heb_mod:.3f} (rp_rs={RP_RS:.4f})")

    # Posterior hesapla
    raw = {
        "TP":  PRIOR_TP  * tp_mod,
        "BEB": PRIOR_BEB * beb_mod,
        "NEB": PRIOR_NEB * neb_mod,
        "HEB": PRIOR_HEB * heb_mod,
    }

    normalized = normalize(raw)

    print(f"\n[3] Prior × Likelihood (normalize edilmemiş)")
    for k, v in raw.items():
        print(f"  {k}: {v:.5f}")

    print(f"\n[4] Posterior (normalize edilmiş)")
    for k, v in normalized.items():
        print(f"  {k}: {v:.4f} ({v*100:.2f}%)")

    fpp = 1.0 - normalized["TP"]
    tp_prob = normalized["TP"]

    print(f"\n{'='*60}")
    print(f"  FPP  = {fpp:.4f} ({fpp*100:.2f}%)")
    print(f"  P(TP) = {tp_prob:.4f} ({tp_prob*100:.2f}%)")
    print(f"{'='*60}")

    # Değerlendirme
    if fpp < 0.01:
        verdict = "VALIDATED — FPP < 1%"
        verdict_en = "Statistically validated planet candidate (FPP < 1%)"
        verdict_tr = "İstatistiksel olarak doğrulanmış gezegen adayı (FPP < %1)"
    elif fpp < 0.05:
        verdict = "STRONG CANDIDATE — FPP < 5%"
        verdict_en = "Strong planet candidate (FPP < 5%)"
        verdict_tr = "Güçlü gezegen adayı (FPP < %5)"
    elif fpp < 0.10:
        verdict = "GOOD CANDIDATE — FPP < 10%"
        verdict_en = "Good planet candidate (FPP < 10%)"
        verdict_tr = "İyi gezegen adayı (FPP < %10)"
    else:
        verdict = "UNCERTAIN"
        verdict_en = "Uncertain — requires further follow-up"
        verdict_tr = "Belirsiz — ek gözlem gerektirir"

    print(f"\n  Karar: {verdict}")
    print(f"  EN: {verdict_en}")
    print(f"  TR: {verdict_tr}")

    # Rapor oluştur
    report = {
        "target": {
            "tic_id": TIC_ID,
            "host_name": HOST_NAME,
            "sector": SECTOR,
        },
        "inputs": {
            "transit_depth_ppm": TRANSIT_DEPTH_PPM,
            "period_days": PERIOD_DAYS,
            "rp_rs": RP_RS,
            "a_over_rs": A_OVER_RS,
            "contamination_ratio": CONTAMINATION_RATIO,
            "host_gmag": HOST_GMAG,
            "n_gaia_neighbors_10arcsec": len(GAIA_NEIGHBORS),
        },
        "methodology": {
            "method": "simplified_scenario_based_fpp",
            "scenarios": ["TP", "BEB", "NEB", "HEB"],
            "prior_tp": PRIOR_TP,
            "prior_beb": PRIOR_BEB,
            "prior_neb": PRIOR_NEB,
            "prior_heb": PRIOR_HEB,
            "notes": [
                "Priors based on general occurrence rates and bright star context.",
                "Likelihood modifiers derived from Gaia neighbor flux analysis, "
                "contamination ratio, and rp/rs constraints.",
                "This is a simplified FPP estimate; triceratops/vespa-level "
                "full MCMC-based FPP recommended for formal publication.",
            ],
        },
        "neighbor_analysis": [
            {
                "source": nb["source"],
                "Gmag": nb["Gmag"],
                "delta_gmag": nb["Gmag"] - HOST_GMAG,
                "flux_ratio": flux_ratio(nb["Gmag"] - HOST_GMAG),
                "max_eclipse_depth_ppm": max_eclipse_depth_for_binary(
                    flux_ratio(nb["Gmag"] - HOST_GMAG)
                ),
                "can_explain_transit": is_depth_consistent(
                    TRANSIT_DEPTH_PPM,
                    max_eclipse_depth_for_binary(
                        flux_ratio(nb["Gmag"] - HOST_GMAG)
                    ),
                ),
            }
            for nb in GAIA_NEIGHBORS
        ],
        "likelihood_modifiers": {
            "TP": tp_mod,
            "BEB": beb_mod,
            "NEB": neb_mod,
            "HEB": heb_mod,
        },
        "raw_posteriors": raw,
        "normalized_posteriors": normalized,
        "results": {
            "FPP": fpp,
            "P_TP": tp_prob,
            "verdict": verdict,
            "verdict_en": verdict_en,
            "verdict_tr": verdict_tr,
        },
    }

    json_path = OUT_DIR / "TIC_417860263_fpp_report.json"
    md_path = OUT_DIR / "TIC_417860263_fpp_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 FPP Report\n\n")
        f.write(f"## Verdict\n")
        f.write(f"- **{verdict}**\n")
        f.write(f"- FPP = **{fpp*100:.2f}%**\n")
        f.write(f"- P(TP) = **{tp_prob*100:.2f}%**\n\n")
        f.write(f"## Inputs\n")
        for k, v in report["inputs"].items():
            f.write(f"- **{k}**: {v}\n")
        f.write(f"\n## Posteriors\n")
        for k, v in normalized.items():
            f.write(f"- **{k}**: {v:.4f} ({v*100:.2f}%)\n")
        f.write(f"\n## Cautions\n")
        for note in report["methodology"]["notes"]:
            f.write(f"- {note}\n")

    print(f"\nSaved: {json_path}")
    print(f"Saved: {md_path}")

    return report


if __name__ == "__main__":
    compute_fpp()