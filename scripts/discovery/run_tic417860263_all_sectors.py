from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

DEFAULT_TARGET = "TIC 417860263"
DEFAULT_SECTORS = [57, 58, 77, 78, 84, 85]


def safe_target_id(target: str) -> str:
    return target.replace(" ", "_").replace("/", "_")


def load_json(path: Path):
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_nested(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def find_sector_result(result, sector: int):
    for sr in getattr(result, "sector_results", []):
        try:
            if getattr(sr, "sector", None) == sector:
                return sr
        except Exception:
            pass
    return None


def sector_result_to_dict(sr):
    if sr is None:
        return {}
    try:
        return sr.summary()
    except Exception:
        return {
            "target_id": getattr(sr, "target_id", None),
            "sector": getattr(sr, "sector", None),
            "success": getattr(sr, "success", None),
            "has_candidate": getattr(sr, "has_candidate", None),
            "candidate_confirmed": getattr(sr, "candidate_confirmed", None),
            "error": getattr(sr, "error", ""),
            "score": getattr(sr, "score", None),
            "class": getattr(sr, "candidate_class", None),
        }


def main():
    parser = argparse.ArgumentParser(
        description="TIC 417860263 için tüm mevcut sektörlerde follow-up çalıştır."
    )
    parser.add_argument(
        "--target",
        default=DEFAULT_TARGET,
        help=f"Hedef adı (varsayılan: {DEFAULT_TARGET})",
    )
    parser.add_argument(
        "--sectors",
        nargs="*",
        type=int,
        default=DEFAULT_SECTORS,
        help=f"Sektör listesi (varsayılan: {' '.join(map(str, DEFAULT_SECTORS))})",
    )
    parser.add_argument(
        "--mcmc",
        action="store_true",
        help="WSL MCMC modu ile çalıştır (çok daha yavaş). Varsayılan MAP.",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Görsel üretimini kapat.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="İsteğe bağlı çıktı dizini override.",
    )
    args = parser.parse_args()

    from astrotransit.settings import load_settings
    from astrotransit.outputs.writers import OutputManager
    from astrotransit.pipelines.tess_pipeline import TESSPipeline

    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = (
            "outputs_tic417860263_allsectors_mcmc"
            if args.mcmc
            else "outputs_tic417860263_allsectors_map"
        )

    config_path = (
        project_root / "configs" / ("wsl_mcmc.toml" if args.mcmc else "default.toml")
    )

    settings = load_settings(config_path)
    settings.general.output_dir = output_dir
    settings.outputs.save_figures = not args.no_viz

    output_manager = OutputManager(settings=settings)

    pipe = TESSPipeline(
        settings=settings,
        output_manager=output_manager,
        force_mcmc=args.mcmc,
        force_map=not args.mcmc,
        skip_visualization=args.no_viz,
        skip_catalog=False,
    )

    print("=" * 72)
    print("TIC 417860263 Çok-Sektör Takibi Başlıyor")
    print("=" * 72)
    print(f"Hedef       : {args.target}")
    print(f"Sektörler   : {args.sectors}")
    print(f"Mod         : {'MCMC' if args.mcmc else 'MAP'}")
    print(f"Output dir  : {output_dir}")
    print("=" * 72)

    try:
        result = pipe.run_target(args.target, sectors=args.sectors)
    finally:
        try:
            pipe.close()
        finally:
            try:
                output_manager.close()
            except Exception:
                pass

    safe_id = safe_target_id(args.target)
    out_root = Path(output_dir)
    out_reports = out_root / "reports"
    out_reports.mkdir(parents=True, exist_ok=True)

    rows = []
    confirmed_count = 0
    success_count = 0

    for sector in args.sectors:
        sr = find_sector_result(result, sector)
        sr_dict = sector_result_to_dict(sr)

        json_path = out_root / "json" / f"{safe_id}_S{sector:02d}.json"
        candidate_json = load_json(json_path)

        row = {
            "target_id": args.target,
            "sector": sector,
            "run_success": sr_dict.get("success"),
            "has_candidate": sr_dict.get("has_candidate"),
            "candidate_confirmed": sr_dict.get("candidate_confirmed"),
            "class": sr_dict.get("class"),
            "score": sr_dict.get("score"),
            "error": sr_dict.get("error", ""),
            "candidate_json_exists": json_path.exists(),
            "candidate_json_path": str(json_path) if json_path.exists() else "",
            "fit_method": None,
            "period_days": None,
            "period_err_days": None,
            "rp_rs": None,
            "rp_rs_err": None,
            "duration_hours": None,
            "depth_ppm": None,
            "snr_adopted": None,
            "fpp": None,
            "r_hat_max": None,
            "n_divergences": None,
            "mcmc_converged": None,
        }

        if sr_dict.get("success"):
            success_count += 1
        if sr_dict.get("candidate_confirmed"):
            confirmed_count += 1

        if candidate_json:
            row["fit_method"] = get_nested(candidate_json, "modeling", "fit_method")
            row["period_days"] = get_nested(candidate_json, "parameters", "period_days")
            row["period_err_days"] = get_nested(
                candidate_json, "parameters", "period_err_days"
            )
            row["rp_rs"] = get_nested(candidate_json, "parameters", "rp_rs")
            row["rp_rs_err"] = get_nested(candidate_json, "parameters", "rp_rs_err")
            row["duration_hours"] = get_nested(
                candidate_json, "parameters", "duration_hours"
            )
            row["depth_ppm"] = get_nested(candidate_json, "parameters", "depth_ppm")
            row["snr_adopted"] = get_nested(candidate_json, "quality", "snr_adopted")
            row["fpp"] = get_nested(candidate_json, "vetting", "fpp")
            row["r_hat_max"] = get_nested(candidate_json, "modeling", "r_hat_max")
            row["n_divergences"] = get_nested(
                candidate_json, "modeling", "n_divergences"
            )
            row["mcmc_converged"] = get_nested(
                candidate_json, "modeling", "mcmc_converged"
            )
            # JSON içindeki score/class değerleri sector_result değerlerini ezebilir
            row["class"] = get_nested(candidate_json, "score", "candidate_class", default=row["class"])
            row["score"] = get_nested(candidate_json, "score", "total_score", default=row["score"])

        rows.append(row)

    summary = {
        "target": args.target,
        "sectors_requested": args.sectors,
        "mode": "mcmc" if args.mcmc else "map",
        "output_dir": output_dir,
        "run_summary": {
            "success": getattr(result, "success", True),
            "sectors_processed": len(args.sectors),
            "sector_runs_successful": success_count,
            "candidates_confirmed": confirmed_count,
        },
        "rows": rows,
    }

    # JSON
    json_summary_path = out_reports / "TIC_417860263_all_sectors_summary.json"
    with open(json_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # CSV
    csv_summary_path = out_reports / "TIC_417860263_all_sectors_summary.csv"
    fieldnames = list(rows[0].keys()) if rows else []
    with open(csv_summary_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Markdown
    md_summary_path = out_reports / "TIC_417860263_all_sectors_summary.md"
    with open(md_summary_path, "w", encoding="utf-8") as f:
        f.write("# TIC 417860263 All-Sectors Summary\n\n")
        f.write(f"- **target**: {args.target}\n")
        f.write(f"- **sectors_requested**: {args.sectors}\n")
        f.write(f"- **mode**: {'mcmc' if args.mcmc else 'map'}\n")
        f.write(f"- **output_dir**: {output_dir}\n")
        f.write(f"- **sector_runs_successful**: {success_count}/{len(args.sectors)}\n")
        f.write(f"- **candidates_confirmed**: {confirmed_count}/{len(args.sectors)}\n\n")

        f.write("## Per-Sector Results\n\n")
        f.write(
            "| Sector | Success | Confirmed | Class | Score | Fit | Period (d) | Rp/Rs | Depth (ppm) | SNR | FPP | r_hat |\n"
        )
        f.write(
            "|---:|:---:|:---:|:---:|---:|:---:|---:|---:|---:|---:|---:|---:|\n"
        )

        for row in rows:
            f.write(
                f"| {row['sector']} "
                f"| {row['run_success']} "
                f"| {row['candidate_confirmed']} "
                f"| {row['class']} "
                f"| {row['score']} "
                f"| {row['fit_method']} "
                f"| {row['period_days']} "
                f"| {row['rp_rs']} "
                f"| {row['depth_ppm']} "
                f"| {row['snr_adopted']} "
                f"| {row['fpp']} "
                f"| {row['r_hat_max']} |\n"
            )

    # Konsol özeti
    print("\n" + "=" * 72)
    print("Kısa Sektör Özeti")
    print("=" * 72)
    for row in rows:
        print(
            f"S{row['sector']:02d} | "
            f"success={row['run_success']} | "
            f"confirmed={row['candidate_confirmed']} | "
            f"class={row['class']} | "
            f"score={row['score']} | "
            f"fit={row['fit_method']} | "
            f"P={row['period_days']} | "
            f"rp/rs={row['rp_rs']} | "
            f"SNR={row['snr_adopted']}"
        )

    print("=" * 72)
    print(f"Saved: {json_summary_path}")
    print(f"Saved: {csv_summary_path}")
    print(f"Saved: {md_summary_path}")
    print("=" * 72)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())