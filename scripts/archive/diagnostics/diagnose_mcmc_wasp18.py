from pathlib import Path
import sys
import time

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

def main():
    from astrotransit.logging_config import setup_logging
    from astrotransit.settings import get_settings
    from astrotransit.data.tess_client import TESSClient
    from astrotransit.data.catalog_client import CatalogClient
    from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
    from astrotransit.detection.cascade import CascadeDetector
    from astrotransit.modeling.parameters import TransitPriors
    from astrotransit.modeling.map_fit import MAPFitter
    from astrotransit.modeling.pymc_fit import PyMCFitter

    setup_logging(log_level="DEBUG")
    settings = get_settings()

    target = "TIC 100100827"
    sector = 2

    print("=" * 72)
    print("  WASP-18b Dogrudan MCMC Teshisi")
    print("=" * 72)

    # Yildiz ozellikleri
    cat = CatalogClient()
    stellar = cat.get_stellar_properties(target)

    stellar_radius = stellar.radius if stellar.is_valid() else 1.35
    stellar_mass = stellar.mass if stellar.is_valid() else 1.20
    stellar_teff = stellar.teff if stellar.teff > 0 else 6226.0

    print(f"[1] Stellar: R={stellar_radius:.3f} Rsun, M={stellar_mass:.3f} Msun, Teff={stellar_teff:.0f} K")

    # Veri
    client = TESSClient(
        author=settings.tess.author,
        exptime=settings.tess.exptime,
        use_cache=settings.tess.use_cache,
    )
    lc = client.get_lightcurve(target, sector=sector)
    print(f"[2] Light curve: {lc.n_points_clean} nokta")

    # Ön işleme
    pre = TESSPreprocessingPipeline(settings=settings)
    preprocessed = pre.run(lc)
    detrended = preprocessed.detrended
    print(f"[3] Detrended: noise={detrended.noise_ppm:.1f} ppm")

    # Tespit
    cascade = CascadeDetector(
        settings=settings,
        stellar_radius=stellar_radius,
        stellar_mass=stellar_mass,
    )
    candidate = cascade.detect(detrended)
    print(f"[4] Candidate: confirmed={candidate.confirmed}, P={candidate.period:.6f}, SNR={candidate.snr:.2f}, SDE={candidate.sde:.2f}")

    if not candidate.confirmed:
        print("HATA: Candidate confirmed degil, MCMC testi anlamsiz")
        return 1

    # Prior
    priors = TransitPriors.from_cascade(
        candidate,
        stellar_radius=stellar_radius,
        stellar_mass=stellar_mass,
        stellar_teff=stellar_teff,
    )

    # MAP
    map_fitter = MAPFitter(max_iterations=2000, n_restarts=3)
    t0 = time.time()
    map_result = map_fitter.fit(
        detrended=detrended,
        priors=priors,
        stellar_radius=stellar_radius,
        stellar_mass=stellar_mass,
        stellar_teff=stellar_teff,
    )
    dt_map = time.time() - t0

    print(f"[5] MAP: success={map_result.success}, P={map_result.period:.6f}, rp/rs={map_result.rp_rs:.6f}, sure={dt_map:.1f}s")

    # DOGRUDAN MCMC
    mcmc = PyMCFitter(
        chains=2,
        draws=300,
        tune=1000,
        target_accept=0.99,
        random_seed=42,
    )

    print("[6] PyMC direct fit basliyor...")
    t1 = time.time()
    mcmc_result = mcmc.fit(
        detrended=detrended,
        priors=priors,
        map_result=map_result,
        stellar_radius=stellar_radius,
        stellar_mass=stellar_mass,
        stellar_teff=stellar_teff,
    )
    dt_mcmc = time.time() - t1

    print()
    print("=" * 72)
    print("  DOGRUDAN MCMC SONUCU")
    print("=" * 72)
    print(f"success         : {mcmc_result.success}")
    print(f"convergence_ok  : {mcmc_result.convergence_ok}")
    print(f"period          : {mcmc_result.period}")
    print(f"period_err      : {mcmc_result.period_err}")
    print(f"rp_rs           : {mcmc_result.rp_rs}")
    print(f"rp_rs_err       : {mcmc_result.rp_rs_err}")
    print(f"impact_parameter: {mcmc_result.impact_parameter}")
    print(f"inclination_deg : {mcmc_result.inclination}")
    print(f"r_hat_max       : {mcmc_result.r_hat_max}")
    print(f"n_divergences   : {mcmc_result.n_divergences}")
    print(f"n_samples       : {mcmc_result.n_samples}")
    print(f"fit_method      : {mcmc_result.fit_method}")
    print(f"sure            : {dt_mcmc:.1f}s")

    if mcmc_result.derived is not None:
        print(f"Rp (R_earth)    : {mcmc_result.derived.planet_radius_rearth}")
        print(f"Teq (K)         : {mcmc_result.derived.equilibrium_temperature_k}")

    if mcmc_result.posteriors:
        print()
        print("Posteriorlar:")
        for key, post in mcmc_result.posteriors.items():
            print(
                f"  {key:18s} median={post.median:.6f} "
                f"std={post.std:.6f} rhat={post.r_hat:.4f} ess={post.ess:.1f}"
            )
    else:
        print("Posteriorlar: BOS")

    print("=" * 72)

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
