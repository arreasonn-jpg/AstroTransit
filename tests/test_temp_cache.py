"""
TempCache birim testleri.

Kapsam
------
- __init__: ttl_hours validasyonu, dizin olusturma, index yukleme
- _make_key: deterministik hash
- _resolve_path: absolute/goreli yol
- register/get_path: ekleme ve okuma
- TTL suresi dolmus kayitlar
- invalidate/cleanup_expired/cleanup_all
- size/stats
- Bozuk indeks dosyasi
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from astrotransit.data.temp_cache import TempCache


@pytest.fixture
def cache(tmp_path: Path) -> TempCache:
    return TempCache(cache_dir=tmp_path / "cache", ttl_hours=24)


def _make_file(directory: Path, name: str = "data.txt", content: str = "x") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / name
    p.write_text(content)
    return p


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_init_creates_cache_dir(tmp_path: Path) -> None:
    target = tmp_path / "new_cache"
    assert not target.exists()
    _cache = TempCache(cache_dir=target)
    assert target.exists()
    assert target.is_dir()


def test_init_rejects_zero_ttl(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ttl_hours pozitif"):
        TempCache(cache_dir=tmp_path / "c", ttl_hours=0)


def test_init_rejects_negative_ttl(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ttl_hours pozitif"):
        TempCache(cache_dir=tmp_path / "c", ttl_hours=-5)


def test_init_default_ttl(tmp_path: Path) -> None:
    c = TempCache(cache_dir=tmp_path / "c")
    assert c.ttl_seconds == 24 * 3600


def test_init_accepts_str_dir(tmp_path: Path) -> None:
    cache = TempCache(cache_dir=str(tmp_path / "c"))
    assert isinstance(cache.cache_dir, Path)


def test_init_initial_size_zero(cache: TempCache) -> None:
    assert cache.size == 0


def test_init_expanduser(tmp_path: Path) -> None:
    c = TempCache(cache_dir=tmp_path / "c")
    assert c.cache_dir.is_absolute()


# ─────────────────────────────────────────────────────────────
# _make_key
# ─────────────────────────────────────────────────────────────

def test_make_key_deterministic() -> None:
    k1 = TempCache._make_key("TIC_123")
    k2 = TempCache._make_key("TIC_123")
    assert k1 == k2


def test_make_key_different_inputs() -> None:
    k1 = TempCache._make_key("A")
    k2 = TempCache._make_key("B")
    assert k1 != k2


def test_make_key_length() -> None:
    k = TempCache._make_key("test")
    assert len(k) == 16


# ─────────────────────────────────────────────────────────────
# _resolve_path
# ─────────────────────────────────────────────────────────────

def test_resolve_path_absolute(cache: TempCache, tmp_path: Path) -> None:
    abs_path = tmp_path / "abs.txt"
    resolved = cache._resolve_path(abs_path)
    assert resolved == abs_path.resolve()


def test_resolve_path_relative(cache: TempCache) -> None:
    resolved = cache._resolve_path("sub/file.txt")
    assert resolved == (cache.cache_dir / "sub" / "file.txt").resolve()


# ─────────────────────────────────────────────────────────────
# register / get_path
# ─────────────────────────────────────────────────────────────

def test_register_then_get(cache: TempCache, tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    cache.register("ident1", f)
    got = cache.get_path("ident1")
    assert got == f.resolve()
    assert cache.size == 1


def test_get_unknown_identifier(cache: TempCache) -> None:
    assert cache.get_path("missing") is None


def test_get_removes_missing_file(cache: TempCache, tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    cache.register("ident", f)
    f.unlink()
    assert cache.get_path("ident") is None
    assert cache.size == 0


def test_register_updates_existing(cache: TempCache, tmp_path: Path) -> None:
    f1 = _make_file(tmp_path, "a.txt")
    f2 = _make_file(tmp_path, "b.txt")
    cache.register("id", f1)
    cache.register("id", f2)
    assert cache.get_path("id") == f2.resolve()
    assert cache.size == 1


# ─────────────────────────────────────────────────────────────
# TTL
# ─────────────────────────────────────────────────────────────

def test_expired_entry_removed(tmp_path: Path) -> None:
    c = TempCache(cache_dir=tmp_path / "c", ttl_hours=1)
    f = _make_file(tmp_path, "expired.txt")
    c.register("exp", f)
    key = c._make_key("exp")
    c._index[key]["timestamp"] = time.time() - 7200
    c._save_index()
    c2 = TempCache(cache_dir=tmp_path / "c", ttl_hours=1)
    got = c2.get_path("exp")
    assert got is None
    assert not f.exists()


def test_valid_entry_within_ttl(cache: TempCache, tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    cache.register("ok", f)
    assert cache.get_path("ok") == f.resolve()


# ─────────────────────────────────────────────────────────────
# invalidate
# ─────────────────────────────────────────────────────────────

def test_invalidate_removes_entry(cache: TempCache, tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    cache.register("id", f)
    assert cache.size == 1
    cache.invalidate("id")
    assert cache.size == 0
    assert not f.exists()


def test_invalidate_missing_is_noop(cache: TempCache) -> None:
    cache.invalidate("ghost")
    assert cache.size == 0


# ─────────────────────────────────────────────────────────────
# cleanup_expired
# ─────────────────────────────────────────────────────────────

def test_cleanup_expired_removes_old(tmp_path: Path) -> None:
    c = TempCache(cache_dir=tmp_path / "c", ttl_hours=1)
    f1 = _make_file(tmp_path, "old.txt")
    f2 = _make_file(tmp_path, "new.txt")
    c.register("old", f1)
    c.register("new", f2)
    key_old = c._make_key("old")
    c._index[key_old]["timestamp"] = time.time() - 7200
    c._save_index()

    n = c.cleanup_expired()
    assert n == 1
    assert not f1.exists()
    assert f2.exists()
    assert c.size == 1


def test_cleanup_expired_nothing(cache: TempCache, tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    cache.register("id", f)
    assert cache.cleanup_expired() == 0


# ─────────────────────────────────────────────────────────────
# cleanup_all
# ─────────────────────────────────────────────────────────────

def test_cleanup_all(cache: TempCache, tmp_path: Path) -> None:
    f1 = _make_file(tmp_path, "a.txt")
    f2 = _make_file(tmp_path, "b.txt")
    cache.register("id1", f1)
    cache.register("id2", f2)
    n = cache.cleanup_all()
    assert n == 2
    assert not f1.exists()
    assert not f2.exists()
    assert cache.size == 0


def test_cleanup_all_empty(cache: TempCache) -> None:
    assert cache.cleanup_all() == 0


# ─────────────────────────────────────────────────────────────
# stats
# ─────────────────────────────────────────────────────────────

def test_stats_empty(cache: TempCache) -> None:
    s = cache.stats()
    assert s["total_entries"] == 0
    assert s["valid_entries"] == 0
    assert s["expired_entries"] == 0
    assert s["total_size_mb"] == 0.0


def test_stats_with_valid_and_expired(tmp_path: Path) -> None:
    c = TempCache(cache_dir=tmp_path / "c", ttl_hours=1)
    # round(x, 2) MB cinsinden yuvarlama yapiyor; >0.005 MB icin buyuk
    # dosya gerekli. ~20 KB yeterli (0.02 MB).
    big = "x" * 20_000
    f1 = _make_file(tmp_path, "valid.txt", big)
    f2 = _make_file(tmp_path, "expired.txt", big)
    c.register("valid", f1)
    c.register("expired", f2)
    key_exp = c._make_key("expired")
    c._index[key_exp]["timestamp"] = time.time() - 7200
    c._save_index()

    s = c.stats()
    assert s["total_entries"] == 2
    assert s["valid_entries"] == 1
    assert s["expired_entries"] == 1
    assert s["total_size_mb"] > 0


def test_stats_ignores_missing_files(cache: TempCache, tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    cache.register("id", f)
    f.unlink()
    s = cache.stats()
    assert s["total_entries"] == 1
    assert s["total_size_mb"] == 0.0


# ─────────────────────────────────────────────────────────────
# Index persistence
# ─────────────────────────────────────────────────────────────

def test_index_persisted_across_instances(tmp_path: Path) -> None:
    f = _make_file(tmp_path)
    c1 = TempCache(cache_dir=tmp_path / "c")
    c1.register("id", f)

    c2 = TempCache(cache_dir=tmp_path / "c")
    assert c2.size == 1
    assert c2.get_path("id") == f.resolve()


def test_corrupt_index_starts_fresh(tmp_path: Path) -> None:
    cache_dir = tmp_path / "c"
    cache_dir.mkdir()
    (cache_dir / "_cache_index.json").write_text("{not valid json")

    c = TempCache(cache_dir=cache_dir)
    assert c.size == 0


def test_index_filters_invalid_entries(tmp_path: Path) -> None:
    cache_dir = tmp_path / "c"
    cache_dir.mkdir()
    bad_data = {
        "valid_key": {
            "identifier": "ok",
            "path": "/some/path",
            "timestamp": 123.0,
        },
        "missing_path": {"timestamp": 123.0},
        "missing_ts": {"path": "/x"},
        "not_dict": "string_value",
    }
    (cache_dir / "_cache_index.json").write_text(json.dumps(bad_data))

    c = TempCache(cache_dir=cache_dir)
    assert c.size == 1
