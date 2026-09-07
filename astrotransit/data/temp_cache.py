"""
Geçici dosya ve cache yönetimi.

İndirilen verileri belirlenen süre boyunca geçici olarak saklar.
Süresi dolan dosyaları otomatik temizler.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Optional

from loguru import logger


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
        self.cache_dir = Path(cache_dir)
        self.ttl_seconds = ttl_hours * 3600
        self._index_file = self.cache_dir / "_cache_index.json"

        # Cache dizinini oluştur
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # İndeksi yükle
        self._index = self._load_index()

        logger.debug(
            f"Cache başlatıldı — dizin: {self.cache_dir}, "
            f"TTL: {ttl_hours} saat, "
            f"mevcut kayıt: {len(self._index)}"
        )

    def _load_index(self) -> dict:
        """Cache indeksini diskten yükler."""

        if self._index_file.exists():
            try:
                with open(self._index_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                logger.warning("Cache indeksi okunamadı, sıfırdan başlatılıyor.")
                return {}
        return {}

    def _save_index(self) -> None:
        """Cache indeksini diske yazar."""

        try:
            with open(self._index_file, "w") as f:
                json.dump(self._index, f, indent=2)
        except IOError as e:
            logger.error(f"Cache indeksi yazılamadı: {e}")

    @staticmethod
    def _make_key(identifier: str) -> str:
        """Tanımlayıcıdan benzersiz cache anahtarı üretir."""

        return hashlib.sha256(identifier.encode()).hexdigest()[:16]

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

        if key not in self._index:
            return None

        entry = self._index[key]
        file_path = Path(entry["path"])

        # Dosya var mı kontrol et
        if not file_path.exists():
            logger.debug(f"Cache dosyası kayıp: {identifier}")
            del self._index[key]
            self._save_index()
            return None

        # TTL kontrolü
        age = time.time() - entry["timestamp"]
        if age > self.ttl_seconds:
            logger.debug(f"Cache süresi dolmuş: {identifier} ({age / 3600:.1f} saat)")
            self._remove_file(file_path)
            del self._index[key]
            self._save_index()
            return None

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

        self._index[key] = {
            "identifier": identifier,
            "path": str(file_path),
            "timestamp": time.time(),
        }

        self._save_index()
        logger.debug(f"Cache'e kaydedildi: {identifier}")

    def invalidate(self, identifier: str) -> None:
        """Belirli bir cache kaydını siler."""

        key = self._make_key(identifier)

        if key in self._index:
            file_path = Path(self._index[key]["path"])
            self._remove_file(file_path)
            del self._index[key]
            self._save_index()
            logger.debug(f"Cache silindi: {identifier}")

    def cleanup_expired(self) -> int:
        """
        Süresi dolmuş tüm cache dosyalarını temizler.

        Returns
        -------
        int
            Temizlenen dosya sayısı.
        """

        expired_keys = []
        now = time.time()

        for key, entry in self._index.items():
            age = now - entry["timestamp"]
            if age > self.ttl_seconds:
                expired_keys.append(key)

        for key in expired_keys:
            file_path = Path(self._index[key]["path"])
            self._remove_file(file_path)
            del self._index[key]

        if expired_keys:
            self._save_index()
            logger.info(f"Süresi dolmuş {len(expired_keys)} cache dosyası temizlendi.")

        return len(expired_keys)

    def cleanup_all(self) -> int:
        """
        Tüm cache dosyalarını temizler.

        Returns
        -------
        int
            Temizlenen dosya sayısı.
        """

        count = len(self._index)

        for entry in self._index.values():
            self._remove_file(Path(entry["path"]))

        self._index.clear()
        self._save_index()

        logger.info(f"Tüm cache temizlendi: {count} dosya silindi.")
        return count

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
            file_path = Path(entry["path"])
            if file_path.exists():
                total_size += file_path.stat().st_size
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