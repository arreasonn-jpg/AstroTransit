from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from textwrap import dedent

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PACK_DIR = PROJECT_ROOT / "release" / "tic417860263_zenodo_v1"

# Kaynak -> hedef
FILE_MAP: list[tuple[str, str]] = [
    # Final / summary reports
    (
        "outputs_discovery/reports/TIC_417860263_final_report.md",
        "reports/TIC_417860263_final_report.md",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_final_report.json",
        "reports/TIC_417860263_final_report.json",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_fpp_report.md",
        "reports/TIC_417860263_fpp_report.md",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_fpp_report.json",
        "reports/TIC_417860263_fpp_report.json",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_crosscheck.md",
        "reports/TIC_417860263_crosscheck.md",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_crosscheck.json",
        "reports/TIC_417860263_crosscheck.json",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_exoplanet_archive_check.md",
        "reports/TIC_417860263_exoplanet_archive_check.md",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_exoplanet_archive_check.json",
        "reports/TIC_417860263_exoplanet_archive_check.json",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_toi_check.md",
        "reports/TIC_417860263_toi_check.md",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_toi_check.json",
        "reports/TIC_417860263_toi_check.json",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_toi_nearby_check.md",
        "reports/TIC_417860263_toi_nearby_check.md",
    ),
    (
        "outputs_discovery/reports/TIC_417860263_toi_nearby_check.json",
        "reports/TIC_417860263_toi_nearby_check.json",
    ),
    # Refined multi-sector validation
    (
        "outputs_tic417860263_refined_validation/reports/TIC_417860263_refined_validation.md",
        "reports/TIC_417860263_refined_validation.md",
    ),
    (
        "outputs_tic417860263_refined_validation/reports/TIC_417860263_refined_validation.json",
        "reports/TIC_417860263_refined_validation.json",
    ),
    # Data products
    (
        "outputs_novel_followup/json/TIC_417860263_S57.json",
        "data_products/TIC_417860263_S57_map.json",
    ),
    (
        "outputs_novel_mcmc/json/TIC_417860263_S57.json",
        "data_products/TIC_417860263_S57_mcmc_candidate.json",
    ),
    (
        "outputs_novel_mcmc/json/TIC_417860263_S57_mcmc_summary.json",
        "data_products/TIC_417860263_S57_mcmc_summary.json",
    ),
    # Config
    ("configs/default.toml", "configs/default.toml"),
    ("configs/wsl_mcmc.toml", "configs/wsl_mcmc.toml"),
]

FIGURE_MAP: list[tuple[str, str]] = [
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_summary.png", "figures/S57_summary.png"),
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_folded.png", "figures/S57_folded.png"),
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_lightcurve.png", "figures/S57_lightcurve.png"),
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_residuals.png", "figures/S57_residuals.png"),
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_scorecard.png", "figures/S57_scorecard.png"),
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_timing.png", "figures/S57_timing.png"),
    ("outputs_novel_mcmc/figures/TIC_417860263_S57_bls_tls_comparison.png", "figures/S57_bls_tls_comparison.png"),
    ("outputs_tic417860263_refined_validation/figures/OC_diagram.png", "figures/OC_diagram.png"),
    ("outputs_tic417860263_refined_validation/figures/phasefold_S57.png", "figures/phasefold_S57.png"),
    ("outputs_tic417860263_refined_validation/figures/phasefold_S58.png", "figures/phasefold_S58.png"),
    ("outputs_tic417860263_refined_validation/figures/phasefold_S77.png", "figures/phasefold_S77.png"),
    ("outputs_tic417860263_refined_validation/figures/phasefold_S78.png", "figures/phasefold_S78.png"),
    ("outputs_tic417860263_refined_validation/figures/phasefold_S84.png", "figures/phasefold_S84.png"),
    ("outputs_tic417860263_refined_validation/figures/phasefold_S85.png", "figures/phasefold_S85.png"),
]


def sha256sum(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def copy_if_exists(src_rel: str, dst_rel: str, manifest: list[dict]) -> None:
    src = PROJECT_ROOT / src_rel
    dst = PACK_DIR / dst_rel

    if not src.exists():
        print(f"  [SKIP] missing: {src_rel}")
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

    entry = {
        "path": dst_rel,
        "source": src_rel,
        "size_bytes": dst.stat().st_size,
        "sha256": sha256sum(dst),
    }
    manifest.append(entry)
    print(f"  [OK]   {dst_rel}")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_environment_snapshot() -> None:
    env_dir = PACK_DIR / "environment"
    env_dir.mkdir(parents=True, exist_ok=True)

    write_text(env_dir / "python_version.txt", sys.version + "\n")

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "freeze"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=PROJECT_ROOT,
        )
        write_text(env_dir / "pip_freeze.txt", result.stdout)
        print("  [OK]   environment/pip_freeze.txt")
    except Exception as e:
        print(f"  [SKIP] pip freeze failed: {e}")

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=PROJECT_ROOT,
        )
        git_hash = result.stdout.strip()
        if git_hash:
            write_text(env_dir / "git_commit.txt", git_hash + "\n")
            print("  [OK]   environment/git_commit.txt")
    except Exception as e:
        print(f"  [SKIP] git hash failed: {e}")


def build_discovery_note() -> str:
    today = date.today().isoformat()
    return dedent(
        f"""
        # Discovery Note: TIC 417860263 / HD 224792

        **Date:** {today}  
        **Pipeline:** AstroTransit v0.1.0

        ## Summary

        TIC 417860263 (HD 224792; Gaia DR3 429915991435184000) is currently the strongest
        non-TOI transit candidate identified in the AstroTransit discovery workflow.

        The candidate is based primarily on a strong Sector 57 detection and is supported by:
        - MAP follow-up
        - WSL/Linux MCMC posterior analysis
        - clean catalog cross-checks
        - simplified scenario-based FPP analysis
        - partial multi-sector forced-ephemeris recovery

        ## Host Star

        - **Distance:** ~38.34 pc (~125 light years)
        - **Tmag:** 6.5443
        - **Teff:** 6362 K
        - **R★:** 1.120 R☉
        - **M★:** 1.27 M☉
        - **TIC contamination ratio:** 0.011693 (~1.2%)

        ## Transit Candidate Parameters

        Sector 57 provides the strongest signal.

        - **Period (reference):** ~2.8535 d
        - **Transit depth:** ~630 ppm
        - **Rp/Rs:** ~0.0251
        - **Planet radius:** ~3.07 R⊕
        - **Equilibrium temperature:** ~1438 K
        - **TLS SNR:** ~47.85

        ## MCMC Summary

        - **Platform:** WSL/Linux
        - **Fit method:** PyMC / exoplanet
        - **success:** True
        - **convergence_ok:** True
        - **r_hat_max:** 1.0421
        - **n_divergences:** 0
        - **Period sampled:** No (fixed during controlled Full-A MCMC)

        ## Catalog Cross-Check Status

        The target does **not** appear as:
        - a TOI,
        - a CTOI,
        - a confirmed planet host in the NASA Exoplanet Archive checks used here,
        - or a follow-up target in ExoFOP-TESS records examined during this workflow.

        SIMBAD identifies the host as **PM*** rather than a known exoplanet host.
        Gaia nearby-source checks do not show a comparably bright contaminant within 10 arcsec.

        ## Simplified False Positive Probability

        A simplified scenario-based FPP estimate yields:

        - **P(TP):** 95.34%
        - **FPP:** 4.66%

        This places TIC 417860263 in the **strong candidate** category, not in the
        formally validated or confirmed-planet category.

        ## Multi-Sector Status

        Additional SPOC 120s TESS data exist in sectors:
        **57, 58, 77, 78, 84, 85**

        A refined forced-ephemeris analysis using AstroTransit detrending recovered
        positive transit-like signals in **4 of 6 sectors**:

        - **Detected:** 57, 58, 77, 78
        - **Not clearly recovered:** 84, 85

        Combined forced-ephemeris depth / SNR metrics are strong, but sector-to-sector
        depth consistency is imperfect and odd-even checks remain noisy.

        ## Limitations

        This candidate is **not formally validated** and **not confirmed**.

        Missing ingredients for formal validation include:
        - high-resolution imaging,
        - radial velocity follow-up,
        - and/or a more complete external FPP workflow.

        Multi-sector transit timing refinement was explored, but the current timing
        approach remains too noisy for a definitive long-baseline ephemeris solution.

        ## Current Best Statement

        TIC 417860263 (HD 224792) is a **strong non-TOI sub-Neptune transit candidate**
        identified by AstroTransit, supported by Sector 57 MAP and WSL-based MCMC analysis,
        clean catalog cross-checks, simplified FPP = 4.66%, and partial multi-sector recovery.

        ## Package Contents

        This deposit includes:
        - core reports,
        - candidate JSON data products,
        - MCMC summary artifacts,
        - catalog cross-check outputs,
        - forced multi-sector validation outputs,
        - figures,
        - configs,
        - and environment snapshots.
        """
    ).strip() + "\n"


def build_readme() -> str:
    return dedent(
        """
        # TIC 417860263 / HD 224792 — Zenodo Evidence Pack

        This folder contains the timestamped AstroTransit evidence pack for
        TIC 417860263, a strong non-TOI transit candidate.

        ## Directory Layout

        - `DISCOVERY_NOTE.md` — human-readable summary note
        - `README.md` — this file
        - `.zenodo.json` — Zenodo metadata template
        - `manifest.json` — internal file manifest
        - `SHA256SUMS.txt` — checksum list

        ### Subdirectories
        - `reports/` — JSON/Markdown reports
        - `data_products/` — native pipeline outputs
        - `figures/` — PNG figures
        - `configs/` — configuration files
        - `environment/` — Python + dependency snapshot

        ## Scientific Status

        This package supports the statement that TIC 417860263 is a
        **strong non-TOI transit candidate**, not a confirmed planet.

        ## Intended Use

        - Zenodo archival deposit
        - timestamped priority record
        - technical sharing and citation
        """
    ).strip() + "\n"


def build_zenodo_metadata() -> dict:
    today = date.today().isoformat()
    return {
        "title": (
            "AstroTransit Discovery Note: TIC 417860263 / HD 224792 "
            "as a Strong Non-TOI Transit Candidate"
        ),
        "upload_type": "dataset",
        "publication_date": today,
        "access_right": "open",
        "license": "cc-by-4.0",
        "description": (
            "Evidence package for TIC 417860263 (HD 224792), a strong non-TOI "
            "transit candidate identified by the AstroTransit pipeline. "
            "The deposit includes MAP and WSL-based MCMC outputs, catalog "
            "cross-check reports, simplified false-positive probability analysis, "
            "refined multi-sector forced-ephemeris validation products, figures, "
            "config files, and an environment snapshot. "
            "Current status: strong candidate, not formally validated."
        ),
        "keywords": [
            "exoplanets",
            "TESS",
            "transit photometry",
            "planet candidate",
            "sub-Neptune",
            "MCMC",
            "Bayesian inference",
            "AstroTransit",
            "TIC 417860263",
            "HD 224792",
        ],
        "notes": (
            "Fill in creators manually on Zenodo before publishing. "
            "This candidate is not formally validated and not confirmed."
        ),
        "version": "1.0.0",
    }


def main() -> None:
    print("=" * 72)
    print("Building Zenodo pack for TIC 417860263")
    print("=" * 72)

    ensure_clean_dir(PACK_DIR)

    manifest_files: list[dict] = []

    print("\n[1/5] Copying reports and data products")
    for src_rel, dst_rel in FILE_MAP:
        copy_if_exists(src_rel, dst_rel, manifest_files)

    print("\n[2/5] Copying figures")
    for src_rel, dst_rel in FIGURE_MAP:
        copy_if_exists(src_rel, dst_rel, manifest_files)

    print("\n[3/5] Writing note/readme/metadata")
    write_text(PACK_DIR / "DISCOVERY_NOTE.md", build_discovery_note())
    write_text(PACK_DIR / "README.md", build_readme())
    with open(PACK_DIR / ".zenodo.json", "w", encoding="utf-8") as f:
        json.dump(build_zenodo_metadata(), f, indent=2, ensure_ascii=False)
    print("  [OK]   DISCOVERY_NOTE.md")
    print("  [OK]   README.md")
    print("  [OK]   .zenodo.json")

    print("\n[4/5] Writing environment snapshot")
    write_environment_snapshot()

    print("\n[5/5] Writing manifest + checksums")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "target": "TIC 417860263",
        "host_name": "HD 224792",
        "package_name": "tic417860263_zenodo_v1",
        "files": manifest_files,
    }

    with open(PACK_DIR / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    with open(PACK_DIR / "SHA256SUMS.txt", "w", encoding="utf-8") as f:
        for entry in manifest_files:
            f.write(f"{entry['sha256']}  {entry['path']}\n")

    print("  [OK]   manifest.json")
    print("  [OK]   SHA256SUMS.txt")

    total_files = sum(1 for p in PACK_DIR.rglob("*") if p.is_file())

    print("\n" + "=" * 72)
    print(f"Pack ready: {PACK_DIR}")
    print(f"Total files: {total_files}")
    print("=" * 72)
    print("Next:")
    print("  1) Inspect DISCOVERY_NOTE.md and .zenodo.json")
    print("  2) Zip the folder")
    print("  3) Upload to Zenodo and publish for DOI")
    print("=" * 72)


if __name__ == "__main__":
    main()