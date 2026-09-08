from scripts.validation.build_known_planet_corpus import normalize


def test_known_planet_builder_keeps_explicit_archive_provenance():
    rows = normalize([{
        "tic_id": "123", "pl_name": "Example b", "pl_orbper": "3.2",
        "pl_rade": "2.1", "disc_refname": "Example et al. 2024",
    }], "2026-01-01T00:00:00Z")
    assert rows[0]["reference"] == "Example et al. 2024"
    assert rows[0]["provenance"]["source"] == "NASA Exoplanet Archive"
