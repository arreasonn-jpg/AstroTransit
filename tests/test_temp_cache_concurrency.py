"""TempCache süreç/iplik güvenliği testleri.

Sharded benchmark birden fazla process'in aynı cache kökünü
paylaşmasını gerektirir; last-writer-wins kaybı olmamalı.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from astrotransit.data.temp_cache import TempCache


def _make_file(directory: Path, name: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("x", encoding="utf-8")
    return path


def test_register_merges_concurrent_writers(tmp_path: Path):
    """Aynı kök üzerinde eşzamanlı register'lar kayıp yapmamalı."""

    n_workers = 8
    cache_dir = tmp_path / "shared_cache"

    def _worker(worker_id: int) -> None:
        cache = TempCache(cache_dir=cache_dir, ttl_hours=24)
        for i in range(4):
            identifier = f"TIC_{worker_id}_{i}_sector_14"
            file_path = _make_file(cache_dir / f"w{worker_id}_i{i}", "lc.fits")
            cache.register(identifier, file_path)

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        list(pool.map(_worker, range(n_workers)))

    # En az diskteki indeks kayıtlarını doğrula — hiçbir yazım kaybolmamalı
    final = TempCache(cache_dir=cache_dir, ttl_hours=24)
    assert final.size == n_workers * 4


def test_invalidate_keeps_other_process_entries(tmp_path: Path):
    """A instance'ı geçerli iken B sadece kendi anahtarını silmeli."""

    cache_dir = tmp_path / "shared_cache"
    cache_a = TempCache(cache_dir=cache_dir, ttl_hours=24)
    cache_b = TempCache(cache_dir=cache_dir, ttl_hours=24)
    file_a = _make_file(cache_dir / "a", "a.fits")
    file_b = _make_file(cache_dir / "b", "b.fits")
    cache_a.register("TIC_A_14", file_a)
    cache_b.register("TIC_B_14", file_b)

    cache_b.invalidate("TIC_B_14")

    fresh = TempCache(cache_dir=cache_dir, ttl_hours=24)
    assert fresh.get_path("TIC_A_14") is not None
    assert fresh.get_path("TIC_B_14") is None


def test_lock_file_created_on_mutation(tmp_path: Path):
    cache = TempCache(cache_dir=tmp_path / "c1", ttl_hours=24)
    file_path = _make_file(tmp_path / "files", "lc.fits")
    cache.register("TIC_1_14", file_path)
    assert (tmp_path / "c1" / "_cache_index.lock").exists()


def test_missing_file_cleanup_preserves_other_entries(tmp_path: Path):
    cache_dir = tmp_path / "shared"
    cache = TempCache(cache_dir=cache_dir, ttl_hours=24)
    path_b = _make_file(cache_dir / "b", "b.fits")
    cache.register("TIC_1_14", _make_file(cache_dir / "a", "a.fits"))
    cache.register("TIC_2_15", path_b)
    (cache_dir / "a" / "a.fits").unlink()

    got = cache.get_path("TIC_1_14")  # eksik dosya temizlenmeli
    assert got is None
    # Diğer kayıt hayatta kalmalı
    assert cache.get_path("TIC_2_15") == path_b


def test_stats_counts_missing_files_gracefully(tmp_path: Path):
    cache = TempCache(cache_dir=tmp_path / "c", ttl_hours=24)
    path_used = _make_file(tmp_path / "f2", "b2.fits")
    cache.register("will_disappear", _make_file(tmp_path / "f1", "a.fits"))
    cache.register("stays", path_used)
    # Dosyayı stat öncesi sil; TOCTOU yolunda çökmemeli
    (tmp_path / "f1" / "a.fits").unlink()
    stats = cache.stats()
    assert stats["valid_entries"] == 1
    assert stats["total_entries"] == 2
