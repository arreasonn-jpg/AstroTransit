from pathlib import Path
import sys
import argparse

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))


def main():
    parser = argparse.ArgumentParser(description="Tek novel aday follow-up")
    parser.add_argument("--target", required=True, help="Orn: 'TIC 417860263'")
    parser.add_argument("--sector", required=True, type=int, help="Sektor numarasi")
    parser.add_argument("--mcmc", action="store_true", help="WSL MCMC modunu kullan")
    args = parser.parse_args()

    from astrotransit.settings import load_settings
    from astrotransit.pipelines.tess_pipeline import TESSPipeline
    from astrotransit.outputs.writers import OutputManager

    if args.mcmc:
        config_path = project_root / "configs" / "wsl_mcmc.toml"
        output_dir = "outputs_novel_mcmc"
    else:
        config_path = project_root / "configs" / "default.toml"
        output_dir = "outputs_novel_followup"

    settings = load_settings(config_path)
    settings.general.output_dir = output_dir
    settings.outputs.save_figures = True

    output_manager = OutputManager(settings=settings)

    pipe = TESSPipeline(
        settings=settings,
        output_manager=output_manager,
        force_mcmc=args.mcmc,
        force_map=not args.mcmc,
        skip_visualization=False,
        skip_catalog=False,
    )

    try:
        result = pipe.run_target(args.target, sectors=[args.sector])
    finally:
        pipe.close()

    print("=" * 72)
    print("Novel Follow-up Sonucu")
    print("=" * 72)
    print(result.summary())
    for sr in result.sector_results:
        print(sr.summary())
    print("=" * 72)

    print(f"Cikti dizini: {output_dir}")
    print(f"Gorseller: {output_dir}/figures")
    print(f"JSON: {output_dir}/json")
    print(f"Parquet: {output_dir}/parquet")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())