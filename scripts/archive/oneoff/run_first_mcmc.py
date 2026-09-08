from pathlib import Path
import sys
import time

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


def main():
    from astrotransit.logging_config import setup_logging
    from astrotransit.settings import get_settings
    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    setup_logging(log_level="INFO")
    _settings = get_settings()

    target = "TIC 100100827"
    sector = 2

    print("=" * 70)
    print("  AstroTransit - Ilk MCMC Testi")
    print("=" * 70)
    print(f"  Hedef : {target}")
    print(f"  Sektor: {sector}")
    print("=" * 70)
    print()

    t0 = time.time()

    with AstroTransitOrchestrator(
        force_mcmc=True,
        force_map=False,
        skip_visualization=True,
        skip_catalog=False,
        log_level="INFO",
    ) as orch:
        result = orch.run_single(target, sectors=[sector])

    dt = time.time() - t0

    print()
    print("=" * 70)
    print("  SONUC")
    print("=" * 70)
    print(f"  Sure: {dt:.1f} s")
    print(f"  Basari: {result.success}")
    print(f"  Islenen sektor: {result.sectors_processed}")
    print(f"  Onayli aday: {result.candidates_confirmed}")
    print()

    for sr in result.sector_results:
        print(f"  Sektor {sr.sector}")
        print(f"    has_candidate      : {sr.has_candidate}")
        print(f"    candidate_confirmed: {sr.candidate_confirmed}")

        if sr.candidate is not None:
            print(f"    period             : {sr.candidate.period:.6f} d")
            print(f"    snr                : {sr.candidate.snr:.2f}")
            print(f"    sde                : {sr.candidate.sde:.2f}")

        if sr.fit_result is not None:
            fr = sr.fit_result
            print(f"    fit_method         : {getattr(fr, 'fit_method', '?')}")
            print(f"    fit_success        : {getattr(fr, 'success', False)}")
            print(f"    fitted_period      : {getattr(fr, 'period', 0.0):.6f} d")
            print(f"    fitted_rp_rs       : {getattr(fr, 'rp_rs', 0.0):.6f}")

            if hasattr(fr, "derived") and fr.derived is not None:
                print(f"    Rp (R_earth)       : {fr.derived.planet_radius_rearth:.3f}")
                print(f"    Teq (K)            : {fr.derived.equilibrium_temperature_k:.1f}")

            # MCMC'ye ozgu alanlar
            if hasattr(fr, "convergence_ok"):
                print(f"    convergence_ok     : {fr.convergence_ok}")
            if hasattr(fr, "r_hat_max"):
                print(f"    r_hat_max          : {fr.r_hat_max}")
            if hasattr(fr, "n_divergences"):
                print(f"    n_divergences      : {fr.n_divergences}")
            if hasattr(fr, "n_samples"):
                print(f"    n_samples          : {fr.n_samples}")

        if sr.quality is not None:
            print(f"    class              : {sr.quality.score.candidate_class.value}")
            print(f"    score              : {sr.quality.score.total_score:.1f}")
            print(f"    fpp                : {sr.quality.vetting.false_positive_probability:.4f}")

        print()

    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())