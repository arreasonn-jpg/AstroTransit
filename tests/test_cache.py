"""Geçici cache davranışı testleri."""

from astrotransit.data.temp_cache import TempCache


def test_relative_registered_path_is_resolved_from_cache_dir(tmp_path):
    cache = TempCache(tmp_path / "cache")
    cached_file = tmp_path / "cache" / "data.bin"
    cached_file.write_bytes(b"cached")

    cache.register("relative", "data.bin")

    assert cache.get_path("relative") == cached_file.resolve()
    assert cache.stats()["valid_entries"] == 1


def test_invalid_ttl_is_rejected(tmp_path):
    try:
        TempCache(tmp_path / "cache", ttl_hours=0)
    except ValueError as exc:
        assert "pozitif" in str(exc)
    else:
        raise AssertionError("non-positive cache TTL was accepted")
