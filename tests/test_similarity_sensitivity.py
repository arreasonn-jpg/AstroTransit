from astrotransit.validation.sensitivity import earth_similarity_sensitivity


def test_similarity_sensitivity_returns_rank_stability():
    rows = [
        {"planet_radius_rearth": 1.0, "insolation_s_earth": 1.0, "equilibrium_temperature_k": 255, "semi_major_axis_au": 1.0, "planet_mass_mearth": 1.0, "stellar_teff_k": 5778},
        {"planet_radius_rearth": 1.4, "insolation_s_earth": 1.5, "equilibrium_temperature_k": 300, "semi_major_axis_au": 1.2, "planet_mass_mearth": 2.0, "stellar_teff_k": 5000},
        {"planet_radius_rearth": 0.7, "insolation_s_earth": .5, "equilibrium_temperature_k": 200, "semi_major_axis_au": .7, "planet_mass_mearth": .5, "stellar_teff_k": 4000},
    ]
    report = earth_similarity_sensitivity(rows)
    assert report.n_perturbations == 2
    assert report.kendall_tau_min is not None
    assert 0 <= report.top_k_overlap_min <= 1
