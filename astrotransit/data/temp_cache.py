"""
Geçici dosya ve cache yönetimi.

İndirilen verileri belirlenen süre boyunca geçici olarak saklar.
Süresi dolan dosyaları otomatik temizler.

Dizin koşusu güvenliği
----------------------
Aynı cache kökünü paylaşan birden fazla process (örn. sharded
benchmark shard'ları) aynı indeksi okuyup yazabilir. Yarış
koşullarını önlemek için tüm "indeks oku-değiştir-yaz" işlemleri
`_cache_index.lock` dosyası üzerindeki danışma kilidi (advisory
lock) altında yapılır; yazma anındaki en güncel indeks diskten
yeniden okunur ve harici process'lerin kayıtları korunur.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Optional

from loguru import logger

_INDEX_FILE_NAME = "_cache_index.json"
_LOCK_FILE_NAME = "_cache_index.lock"


class TempCache:
    """
    Geçici dosya cache yöneticisi.

    İndirilen verilerin tekrar tekrar indirilmesini önlemek için
    belirli bir süre boyunca geçici dizinde saklar.

    Parameters
    ----------
    cache_dir : str veya Path
        Cache dizini yolu.
    ttl_hours : int
        Cache geçerlilik süresi (saat).
    """

    def __init__(self, cache_dir: str | Path, ttl_hours: int = 24):
        if ttl_hours <= 0:
            raise ValueError("ttl_hours pozitif olmalıdır.")
        self.cache_dir = Path(cache_dir).expanduser().resolve()
        self.ttl_seconds = float(ttl_hours) * 3600
        self._index_file = self.cache_dir / _INDEX_FILE_NAME
        self._lock_file = self.cache_dir / _LOCK_FILE_NAME

        # Cache dizinini oluştur
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # İndeksi yükle
        self._index = self._load_index()

        logger.debug(
            f"Cache başlatıldı — dizin: {self.cache_dir}, "
            f"TTL: {ttl_hours} saat, "
            f"mevcut kayıt: {len(self._index)}"
        )

    # ── Cross-platform advisory lock ──────────────────────────

    @contextlib.contextmanager
    def _index_lock(self) -> Iterator[None]:
        """İndeks okuma/yazma için süreçler arası danışma kilidi.

        flock (POSIX) veya msvcrt.locking (Windows) desteklenmeyen
        ortamlarda (örn. bazı ağ dosya sistemleri) kilitsiz devam
        edilir; korunma olmuyorsa bile veri bozulmaz, sadece
        eşzamanlı yazım kayıp riski taşır.
        """

        with self._lock_file.open("a") as lock_file:
            locked = self._acquire_lock(lock_file)
            try:
                yield
            finally:
                if locked:
                    self._release_lock(lock_file)

    @staticmethod
    def _acquire_lock(lock_file) -> bool:
        """Dosyada münhasır kilit kurmaya çalışır; başarısızsa False."""

        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            return True
        except (ImportError, OSError) as e:
            logger.debug(f"Cache kilidi kurulamadı (kilitsiz devam): {e}")
            return False

    @staticmethod
    def _release_lock(lock_file) -> None:
        """Münhasır kilit bırakır."""

        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError) as e:
            logger.debug(f"Cache kilidi bırakılamadı: {e}")

    # ── İndeks diske dayalı okuma/yazma ────────────────────────

    def _load_index(self) -> dict:
        """Cache indeksini diskten yükler."""

        if self._index_file.exists():
            try:
                with self._index_file.open("r", encoding="utf-8") as f:
                    value = json.load(f)
                if not isinstance(value, dict):
                    raise ValueError("cache index sözlük değil")
                return {
                    key: entry
                    for key, entry in value.items()
                    if isinstance(entry, dict)
                    and isinstance(entry.get("path"), str)
                    and isinstance(entry.get("timestamp"), (int, float))
                }
            except (json.JSONDecodeError, OSError, ValueError):
                logger.warning("Cache indeksi okunamadı, sıfırdan başlatılıyor.")
                return {}
        return {}

    def _save_index(self) -> None:
        """Cache indeksini atomik olarak diske yazar."""

        temp_path = self._index_file.with_suffix(
            f".tmp.{os.getpid()}"
        )
        try:
            with temp_path.open("w", encoding="utf-8") as f:
                json.dump(self._index, f, indent=2, ensure_ascii=False)
                f.write("\n")
            temp_path.replace(self._index_file)
        except (OSError, TypeError, ValueError) as e:
            logger.error(f"Cache indeksi yazılamadı: {e}")
            with contextlib.suppress(OSError):
                temp_path.unlink(missing_ok=True)

    def _mutate_index(self, mutator: Callable[[dict], None]) -> None:
        """İndeks değişikliğini kilit altında, en güncel disk verisiyle uygular.

        `mutator` en güncel indeks sözlüğünü alır ve yerinde değiştirir.
        Diğer process'lerin kayıtları silinmez; yalnızca bu süreç de
        bilinçli olarak değiştirdiği anahtarlar değişir.
        """

        with self._index_lock():
            self._index = self._load_index()
            mutator(self._index)
            self._save_index()

    def _refresh_index(self) -> dict:
        """Kilit altında indeksi diskten yeniler ve sözlüğü döndürür."""

        with self._index_lock():
            self._index = self._load_index()
            return self._index

    @staticmethod
    def _make_key(identifier: str) -> str:
        """Tanımlayıcıdan benzersiz cache anahtarı üretir."""

        return hashlib.sha256(identifier.encode()).hexdigest()[:16]

    def _resolve_path(self, file_path: str | Path) -> Path:
        """Cache indeksindeki yolu cache köküne göre mutlak hale getirir.

        Eski indekslerde göreli yollar bulunabilir. Bunları çalışma dizinine
        göre yorumlamak, farklı bir process çalışma dizininden cache okununca
        kayıtların kaybolmuş görünmesine neden olur.
        """

        path = Path(file_path).expanduser()
        if not path.is_absolute():
            path = self.cache_dir / path
        return path.resolve()

    def get_path(self, identifier: str) -> Optional[Path]:
        """
        Cache'te geçerli bir dosya varsa yolunu döndürür.

        Parameters
        ----------
        identifier : str
            Benzersiz tanımlayıcı (örn. "TIC_123456789_sector_14").

        Returns
        -------
        Path veya None
            Geçerli cache dosyası varsa yolu, yoksa None.
        """

        key = self._make_key(identifier)

        with self._index_lock():
            index = self._load_index()
            entry = index.get(key)

            if entry is None:
                self._index = index
                return None

            file_path = self._resolve_path(entry["path"])

            # Dosya var mı kontrol et
            if not file_path.exists():
                logger.debug(f"Cache dosyası kayıp: {identifier}")
                index.pop(key)
                self._index = index
                self._save_index()
                return None

            # TTL kontrolü
            age = time.time() - entry["timestamp"]
            if age > self.ttl_seconds:
                logger.debug(f"Cache süresi dolmuş: {identifier} ({age / 3600:.1f} saat)")
                self._remove_file(file_path)
                index.pop(key)
                self._index = index
                self._save_index()
                return None

            self._index = index
            logger.debug(f"Cache geçerli: {identifier}")
            return file_path

    def register(self, identifier: str, file_path: Path) -> None:
        """
        Yeni bir dosyayı cache'e kaydeder.

        Parameters
        ----------
        identifier : str
            Benzersiz tanımlayıcı.
        file_path : Path
            Kaydedilecek dosyanın yolu.
        """

        key = self._make_key(identifier)
        resolved_path = self._resolve_path(file_path)
        entry = {
            "identifier": identifier,
            "path": str(resolved_path),
            "timestamp": time.time(),
        }

        def _set(index: dict) -> None:
            index[key] = entry

        self._mutate_index(_set)
        logger.debug(f"Cache'e kaydedildi: {identifier}")

    def invalidate(self, identifier: str) -> None:
        """Belirli bir cache kaydını siler."""

        key = self._make_key(identifier)

        def _remove(index: dict) -> None:
            entry = index.pop(key, None)
            if entry is not None:
                file_path = self._resolve_path(entry["path"])
                self._remove_file(file_path)
                logger.debug(f"Cache silindi: {identifier}")

        self._mutate_index(_remove)

    def cleanup_expired(self) -> int:
        """
        Süresi dolmuş tüm cache dosyalarını temizler.

        Returns
        -------
        int
            Temizlenen dosya sayısı.
        """

        removed_count = 0

        def _purge(index: dict) -> None:
            nonlocal removed_count
            now = time.time()
            expired = [
                key for key, entry in index.items()
                if now - entry["timestamp"] > self.ttl_seconds
            ]
            for key in expired:
                file_path = self._resolve_path(index[key]["path"])
                self._remove_file(file_path)
                del index[key]
            removed_count = len(expired)

        self._mutate_index(_purge)

        if removed_count:
            logger.info(f"Süresi dolmuş {removed_count} cache dosyası temizlendi.")
        return removed_count

    def cleanup_all(self) -> int:
        """
        Tüm cache dosyalarını temizler.

        Returns
        -------
        int
            Temizlenen dosya sayısı.
        """

        removed_count = 0

        def _purge(index: dict) -> None:
            nonlocal removed_count
            removed_count = len(index)
            for entry in index.values():
                self._remove_file(self._resolve_path(entry["path"]))
            index.clear()

        self._mutate_index(_purge)

        logger.info(f"Tüm cache temizlendi: {removed_count} dosya silindi.")
        return removed_count

    @staticmethod
    def _remove_file(path: Path) -> None:
        """Dosyayı güvenli şekilde siler."""

        try:
            if path.exists():
                path.unlink()
        except OSError as e:
            logger.warning(f"Dosya silinemedi: {path} — {e}")

    @property
    def size(self) -> int:
        """Cache'teki kayıt sayısı."""
        return len(self._index)

    def stats(self) -> dict:
        """Cache istatistiklerini döndürür."""

        total_size = 0
        valid_count = 0
        expired_count = 0
        now = time.time()

        for entry in self._index.values():
            file_path = self._resolve_path(entry["path"])
            try:
                file_size = file_path.stat().st_size
            except OSError:
                # Dosya, varlık kontrolü ile stat arasında silindiyse atla.
                continue
            total_size += file_size
            age = now - entry["timestamp"]
            if age <= self.ttl_seconds:
                valid_count += 1
            else:
                expired_count += 1

        return {
            "total_entries": len(self._index),
            "valid_entries": valid_count,
            "expired_entries": expired_count,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
        }


__all__ = ["TempCache"]
