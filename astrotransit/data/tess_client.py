"""
TESS veri erişim istemcisi.

MAST arşivinden TESS light curve verilerini indirir, kalite maskeleri
uygular ve temiz veri nesneleri döndürür.

Kullanılan veri ürünleri (Faz 1):
    - SPOC 2-dakika light curve
    - SPOC 20-saniye light curve (opsiyonel)

Sonraki fazlarda eklenecek:
    - Target Pixel Files (TPF)
    - Full Frame Images (FFI)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
import zipfile
from typing import Any, Optional

import numpy as np
from loguru import logger

try:  # Import is intentionally lazy-friendly: data models work offline.
    import lightkurve as lk
except ImportError:  # pragma: no cover - exercised only in minimal installs
    lk = None

from astrotransit.data.temp_cache import TempCache
from astrotransit.data.mast_client import MASTClient
from astrotransit.utils.identifiers import normalize_tic_id, extract_tic_number


# ──────────────────────────────────────
# Veri modeli
# ──────────────────────────────────────
@dataclass
class TESSLightCurveData:
    """
    Temizlenmiş TESS light curve verisi.

    Bu nesne pipeline boyunca taşınan temel veri birimidir.

    Attributes
    ----------
    target_id : str
        Standart TIC ID (örn. "TIC 123456789").
    sector : int
        TESS sektör numarası.
    time : np.ndarray
        Zaman dizisi (BTJD formatında).
    flux : np.ndarray
        Normalize edilmemiş akı değerleri.
    flux_err : np.ndarray
        Akı hata değerleri.
    quality : np.ndarray
        Kalite bayrakları.
    cadence : float
        Kadans (saniye).
    time_format : str
        Zaman formatı bilgisi.
    meta : dict
        Ek metadata bilgileri.
    n_points_raw : int
        Temizlenmeden önceki veri noktası sayısı.
    n_points_clean : int
        Temizlendikten sonraki veri noktası sayısı.
    """

    target_id: str
    sector: int
    time: np.ndarray
    flux: np.ndarray
    flux_err: np.ndarray
    quality: np.ndarray
    cadence: float
    time_format: str = "btjd"
    meta: dict = field(default_factory=dict)
    n_points_raw: int = 0
    n_points_clean: int = 0

    @property
    def duration_days(self) -> float:
        """Gözlem süresi (gün)."""
        if len(self.time) < 2:
            return 0.0
        return float(self.time[-1] - self.time[0])

    @property
    def completeness(self) -> float:
        """Veri tamlığı oranı (0-1)."""
        if self.n_points_raw == 0:
            return 0.0
        return self.n_points_clean / self.n_points_raw

    @property
    def median_flux(self) -> float:
        """Medyan akı değeri."""
        if len(self.flux) == 0:
            return 0.0
        return float(np.nanmedian(self.flux))

    def summary(self) -> dict:
        """Özet bilgileri sözlük olarak döndürür."""
        return {
            "target_id": self.target_id,
            "sector": self.sector,
            "cadence_sec": self.cadence,
            "duration_days": round(self.duration_days, 2),
            "n_points_raw": self.n_points_raw,
            "n_points_clean": self.n_points_clean,
            "completeness": round(self.completeness, 4),
            "median_flux": round(self.median_flux, 4),
            "time_format": self.time_format,
        }


@dataclass
class TESSMultiSectorData:
    """
    Birden fazla sektörden gelen light curve verilerini tutar.

    Attributes
    ----------
    target_id : str
        Standart TIC ID.
    sectors : list[TESSLightCurveData]
        Sektör bazlı temiz light curve listesi.
    """

    target_id: str
    sectors: list[TESSLightCurveData] = field(default_factory=list)

    @property
    def n_sectors(self) -> int:
        """Toplam sektör sayısı."""
        return len(self.sectors)

    @property
    def sector_numbers(self) -> list[int]:
        """Sektör numaraları listesi."""
        return [s.sector for s in self.sectors]

    @property
    def total_duration_days(self) -> float:
        """Toplam gözlem süresi (gün)."""
        return sum(s.duration_days for s in self.sectors)

    @property
    def total_points(self) -> int:
        """Toplam temiz veri noktası sayısı."""
        return sum(s.n_points_clean for s in self.sectors)

    def summary(self) -> dict:
        """Özet bilgileri döndürür."""
        return {
            "target_id": self.target_id,
            "n_sectors": self.n_sectors,
            "sectors": self.sector_numbers,
            "total_duration_days": round(self.total_duration_days, 2),
            "total_clean_points": self.total_points,
        }


# ──────────────────────────────────────
# Hata sınıfları
# ──────────────────────────────────────
class TESSDataError(Exception):
    """TESS veri erişim hatası."""
    pass


class TESSNoDataError(TESSDataError):
    """Hedef için TESS verisi bulunamadı."""
    pass


class TESSQualityError(TESSDataError):
    """Veri kalite kontrolünden geçemedi."""
    pass


# ──────────────────────────────────────
# Ana istemci sınıfı
# ──────────────────────────────────────
class TESSClient:
    """
    TESS light curve veri erişim istemcisi.

    MAST arşivinden light curve verilerini indirir, kalite maskesi
    uygular ve temiz TESSLightCurveData nesneleri döndürür.

    Parameters
    ----------
    author : str
        Light curve üreticisi. Varsayılan "SPOC".
    exptime : int
        Kadans (saniye). 20, 120 veya 600.
    quality_bitmask : str
        Kalite maskesi. "default", "hard", "hardest".
    cache_dir : str veya Path
        Geçici cache dizini.
    cache_ttl_hours : int
        Cache geçerlilik süresi (saat).
    use_cache : bool
        Cache kullanılsın mı.

    Örnekler
    --------
    >>> client = TESSClient()
    >>> lc_data = client.get_lightcurve("TIC 261136679", sector=14)
    >>> print(lc_data.summary())
    """

    def __init__(
        self,
        author: str = "SPOC",
        exptime: int = 120,
        quality_bitmask: str = "default",
        cache_dir: str | Path = ".cache/astrotransit/tess",
        cache_ttl_hours: int = 24,
        use_cache: bool = True,
    ):
        self.author = author
        self.exptime = exptime
        self.quality_bitmask = quality_bitmask
        self.use_cache = use_cache

        # Cache yöneticisi
        self._cache = TempCache(
            cache_dir=cache_dir,
            ttl_hours=cache_ttl_hours,
        ) if use_cache else None

        # MAST istemcisi
        self._mast = MASTClient()

        logger.info(
            f"TESSClient başlatıldı — author: {author}, "
            f"exptime: {exptime}s, "
            f"quality: {quality_bitmask}, "
            f"cache: {'açık' if use_cache else 'kapalı'}"
        )

    def search(
        self,
        target: str | int,
        sector: Optional[int] = None,
    ) -> lk.SearchResult:
        """
        TESS light curve arar.

        Parameters
        ----------
        target : str veya int
            TIC ID veya hedef adı.
        sector : int, opsiyonel
            Belirli sektör. Verilmezse tüm sektörler aranır.

        Returns
        -------
        lightkurve.SearchResult
            Bulunan light curve sonuçları.

        Raises
        ------
        TESSNoDataError
            Veri bulunamazsa.
        """

        if lk is None:
            raise TESSDataError(
                "Lightkurve bağımlılığı kullanılamıyor. "
                "Kurulumu tamamlamak için 'pip install lightkurve' çalıştırın."
            )

        # TIC ID standardizasyonu
        if isinstance(target, int):
            target_str = normalize_tic_id(target)
        else:
            target_str = target

        logger.info(
            f"TESS araması başlatılıyor — hedef: {target_str}, "
            f"sektör: {sector if sector else 'tümü'}"
        )

        import time as _time

        search_result = None

        for attempt in range(3):
            try:
                search_result = lk.search_lightcurve(
                    target_str,
                    mission="TESS",
                    author=self.author,
                    exptime=self.exptime,
                    sector=sector,
                )
                break
            except Exception as e:
                wait = 2 ** attempt  # 1, 2, 4 saniye
                if attempt < 2:
                    logger.warning(
                        f"TESS arama denemesi {attempt+1}/3 başarısız: {e}. "
                        f"{wait}s bekleyip tekrar denenecek..."
                    )
                    _time.sleep(wait)
                else:
                    raise TESSDataError(f"TESS araması başarısız: {e}") from e

        if search_result is None or len(search_result) == 0:
            raise TESSNoDataError(
                f"'{target_str}' için TESS verisi bulunamadı "
                f"(sektör: {sector if sector else 'tümü'}, "
                f"author: {self.author}, exptime: {self.exptime}s)."
            )

        logger.info(f"Arama tamamlandı: {len(search_result)} light curve bulundu.")
        return search_result

    def download_lightcurve(
        self,
        search_result: lk.SearchResult,
        index: int = 0,
    ) -> lk.LightCurve:
        """
        Arama sonucundan light curve indirir.

        Parameters
        ----------
        search_result : lightkurve.SearchResult
            Arama sonucu.
        index : int
            İndirilecek sonucun indeksi.

        Returns
        -------
        lightkurve.LightCurve
            İndirilen light curve.
        """

        if index < 0 or index >= len(search_result):
            raise TESSDataError(
                f"İndeks {index} geçersiz. "
                f"Arama sonucunda {len(search_result)} kayıt var."
            )

        logger.info(f"Light curve indiriliyor: indeks {index}...")

        try:
            lc = search_result[index].download(
                quality_bitmask=self.quality_bitmask,
            )
        except Exception as e:
            raise TESSDataError(f"Light curve indirme başarısız: {e}") from e

        if lc is None:
            raise TESSDataError("Light curve indirme başarısız: None döndü.")

        logger.info(
            f"Light curve indirildi — "
            f"{len(lc.time)} veri noktası, "
            f"sektör: {lc.meta.get('SECTOR', 'bilinmiyor')}"
        )

        return lc

    def _clean_lightcurve(
        self,
        lc: lk.LightCurve,
        sigma_upper: float = 5.0,
        sigma_lower: float = 5.0,
    ) -> lk.LightCurve:
        """
        Light curve üzerinde temel temizleme işlemleri uygular.

        İşlemler:
            1. NaN değerleri kaldırma
            2. Sonsuz değerleri kaldırma
            3. Sıfır ve negatif akı değerlerini kaldırma
            4. Sigma kırpma (aykırı değer temizliği)

        Parameters
        ----------
        lc : lightkurve.LightCurve
            Ham light curve.
        sigma_upper : float
            Üst sigma kırpma eşiği.
        sigma_lower : float
            Alt sigma kırpma eşiği.

        Returns
        -------
        lightkurve.LightCurve
            Temizlenmiş light curve.
        """

        n_initial = len(lc.time)
        logger.debug(f"Temizleme başlıyor — başlangıç: {n_initial} nokta")

        # 1. NaN temizleme
        lc = lc.remove_nans()
        logger.debug(f"NaN temizleme sonrası: {len(lc.time)} nokta")

        # 2. Sonsuz değerleri kaldır
        finite_mask = np.isfinite(self._value_array(lc.flux))
        if hasattr(lc, 'flux_err') and lc.flux_err is not None:
            finite_mask &= np.isfinite(self._value_array(lc.flux_err))
        lc = lc[finite_mask]
        logger.debug(f"Sonsuz değer temizleme sonrası: {len(lc.time)} nokta")

        # 3. Sıfır ve negatif akı temizleme
        positive_mask = self._value_array(lc.flux) > 0
        lc = lc[positive_mask]
        logger.debug(f"Sıfır/negatif temizleme sonrası: {len(lc.time)} nokta")

        # 4. Sigma kırpma
        if len(lc.time) > 10:  # çok az veri varsa sigma kırpma yapma
            lc = lc.remove_outliers(
                sigma_upper=sigma_upper,
                sigma_lower=sigma_lower,
            )
            logger.debug(f"Sigma kırpma sonrası: {len(lc.time)} nokta")

        n_final = len(lc.time)
        n_removed = n_initial - n_final
        pct_removed = (n_removed / n_initial * 100) if n_initial > 0 else 0

        logger.info(
            f"Temizleme tamamlandı — "
            f"başlangıç: {n_initial}, "
            f"son: {n_final}, "
            f"çıkarılan: {n_removed} ({pct_removed:.1f}%)"
        )

        return lc

    @staticmethod
    def _value_array(value: Any) -> np.ndarray:
        """Astropy Quantity/Time veya ndarray değerini NumPy dizisine çevirir."""

        return np.asarray(getattr(value, "value", value))

    def _to_data_object(
        self,
        lc: lk.LightCurve,
        target_id: str,
        n_raw: int,
    ) -> TESSLightCurveData:
        """
        Lightkurve nesnesini standart TESSLightCurveData'ya dönüştürür.

        Parameters
        ----------
        lc : lightkurve.LightCurve
            Temizlenmiş light curve.
        target_id : str
            Standart TIC ID.
        n_raw : int
            Temizlenmeden önceki nokta sayısı.

        Returns
        -------
        TESSLightCurveData
            Standart veri nesnesi.
        """

        # Zaman ve akı dizilerini çıkar
        time_arr = np.array(self._value_array(lc.time), dtype=np.float64)
        flux_arr = np.array(self._value_array(lc.flux), dtype=np.float64)

        # Hata dizisi
        if hasattr(lc, 'flux_err') and lc.flux_err is not None:
            flux_err_arr = np.array(self._value_array(lc.flux_err), dtype=np.float64)
        else:
            # Hata yoksa medyan akının sabit bir oranı olarak tahmin et
            flux_err_arr = np.full_like(flux_arr, np.nanmedian(flux_arr) * 1e-4)
            logger.warning("Akı hatası bulunamadı, sabit tahmin kullanılıyor.")

        # Kalite bayrakları
        if hasattr(lc, 'quality') and lc.quality is not None:
            quality_arr = np.array(self._value_array(lc.quality), dtype=np.int32)
        else:
            quality_arr = np.zeros(len(time_arr), dtype=np.int32)

        # Metadata
        meta = {}
        if hasattr(lc, 'meta') and lc.meta:
            for key in ['SECTOR', 'CAMERA', 'CCD', 'TEFF', 'LOGG', 'RADIUS',
                        'TMAG', 'RA_OBJ', 'DEC_OBJ', 'TICID', 'LABEL']:
                if key in lc.meta:
                    value = lc.meta[key]
                    # numpy tiplerini Python tiplerine dönüştür
                    if hasattr(value, 'item'):
                        value = value.item()
                    meta[key] = value

        sector = lc.meta.get('SECTOR', -1) if hasattr(lc, 'meta') else -1

        return TESSLightCurveData(
            target_id=target_id,
            sector=int(sector),
            time=time_arr,
            flux=flux_arr,
            flux_err=flux_err_arr,
            quality=quality_arr,
            cadence=float(self.exptime),
            time_format="btjd",
            meta=meta,
            n_points_raw=n_raw,
            n_points_clean=len(time_arr),
        )

    def _cache_identifier(
        self,
        target_id: str,
        sector: Optional[int],
        sigma_upper: float = 5.0,
        sigma_lower: float = 5.0,
    ) -> str:
        """Temizlenmiş light curve için tüm sonucu tanımlayan cache anahtarı."""

        tic_num = extract_tic_number(target_id)
        sector_str = f"s{sector}" if sector is not None else "all"
        return (
            f"tess_lc_{tic_num}_{sector_str}_{self.author}_{self.exptime}_"
            f"{self.quality_bitmask}_{sigma_upper:g}_{sigma_lower:g}"
        )

    @staticmethod
    def _row_value(row: Any, name: str, default: Any = None) -> Any:
        """Astropy Row ve dict nesnelerinden değer okur."""

        if row is None:
            return default
        try:
            if name in row.colnames:  # astropy Row
                return row[name]
        except AttributeError:
            pass
        if isinstance(row, dict):
            return row.get(name, default)
        try:
            return row[name]
        except (KeyError, IndexError, TypeError):
            return default

    @classmethod
    def _sector_from_row(cls, row: Any) -> Optional[int]:
        """Lightkurve arama satırından sektör numarasını çıkarır."""

        for name in ("sector", "sequence_number"):
            value = cls._row_value(row, name)
            if value not in (None, ""):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
        mission = str(cls._row_value(row, "mission", ""))
        match = re.search(r"sector\s*(\d+)", mission, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
        obs_id = str(cls._row_value(row, "obs_id", ""))
        match = re.search(r"s(?:ector)?[-_ ]?(\d+)", obs_id, flags=re.IGNORECASE)
        return int(match.group(1)) if match else None

    def _cache_path(self, identifier: str) -> Optional[Path]:
        if self._cache is None:
            return None
        return self._cache.cache_dir / f"{TempCache._make_key(identifier)}.npz"

    def _load_cached_data(self, identifier: str) -> Optional[TESSLightCurveData]:
        """Cache'teki temiz light curve'ü güvenle okur."""

        if self._cache is None:
            return None
        path = self._cache.get_path(identifier)
        if path is None:
            return None
        try:
            with np.load(path, allow_pickle=False) as archive:
                meta = json.loads(str(archive["meta_json"].item()))
                return TESSLightCurveData(
                    target_id=str(meta["target_id"]),
                    sector=int(meta["sector"]),
                    time=np.asarray(archive["time"], dtype=np.float64),
                    flux=np.asarray(archive["flux"], dtype=np.float64),
                    flux_err=np.asarray(archive["flux_err"], dtype=np.float64),
                    quality=np.asarray(archive["quality"], dtype=np.int32),
                    cadence=float(meta["cadence"]),
                    time_format=str(meta.get("time_format", "btjd")),
                    meta=dict(meta.get("meta", {})),
                    n_points_raw=int(meta["n_points_raw"]),
                    n_points_clean=int(meta["n_points_clean"]),
                )
        except (
            OSError,
            EOFError,
            zipfile.BadZipFile,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            logger.warning(f"Bozuk TESS cache kaydı temizleniyor: {identifier} ({exc})")
            self._cache.invalidate(identifier)
            return None

    def _store_cached_data(self, identifier: str, data: TESSLightCurveData) -> None:
        """Temiz light curve'ü atomik olarak cache'e yazar."""

        if self._cache is None:
            return
        path = self._cache_path(identifier)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp.npz")
        meta = {
            "target_id": data.target_id,
            "sector": data.sector,
            "cadence": data.cadence,
            "time_format": data.time_format,
            "meta": data.meta,
            "n_points_raw": data.n_points_raw,
            "n_points_clean": data.n_points_clean,
        }
        try:
            np.savez_compressed(
                temp_path,
                time=np.asarray(data.time, dtype=np.float64),
                flux=np.asarray(data.flux, dtype=np.float64),
                flux_err=np.asarray(data.flux_err, dtype=np.float64),
                quality=np.asarray(data.quality, dtype=np.int32),
                meta_json=json.dumps(meta, ensure_ascii=False, default=str),
            )
            temp_path.replace(path)
            self._cache.register(identifier, path)
        except (OSError, TypeError, ValueError) as exc:
            logger.warning(f"TESS cache yazılamadı: {identifier} ({exc})")
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def get_lightcurve(
        self,
        target: str | int,
        sector: Optional[int] = None,
        sigma_upper: float = 5.0,
        sigma_lower: float = 5.0,
    ) -> TESSLightCurveData:
        """
        Tek bir sektör için TESS light curve verisini alır ve temizler.

        Tam iş akışı:
            1. Arama
            2. İndirme
            3. Temizleme
            4. Standart formata dönüştürme

        Parameters
        ----------
        target : str veya int
            TIC ID veya hedef adı.
        sector : int, opsiyonel
            Belirli sektör numarası.
        sigma_upper : float
            Üst aykırı değer eşiği.
        sigma_lower : float
            Alt aykırı değer eşiği.

        Returns
        -------
        TESSLightCurveData
            Temizlenmiş standart light curve verisi.

        Örnekler
        --------
        >>> client = TESSClient()
        >>> data = client.get_lightcurve("TIC 261136679", sector=14)
        >>> print(data.summary())
        """

        # Hedef standardizasyonu
        target_id = normalize_tic_id(target) if isinstance(target, (int, str)) else str(target)
        cache_id = self._cache_identifier(
            target_id,
            sector,
            sigma_upper=sigma_upper,
            sigma_lower=sigma_lower,
        )

        logger.info(f"Light curve alınıyor — hedef: {target_id}, sektör: {sector}")

        cached = self._load_cached_data(cache_id)
        if cached is not None:
            logger.info(f"TESS light curve cache'ten yüklendi — {target_id} sektör {cached.sector}")
            return cached

        # Ara → İndir → Temizle → Dönüştür
        search_result = self.search(target_id, sector=sector)
        raw_lc = self.download_lightcurve(search_result, index=0)
        n_raw = len(raw_lc.time)

        clean_lc = self._clean_lightcurve(
            raw_lc,
            sigma_upper=sigma_upper,
            sigma_lower=sigma_lower,
        )

        data = self._to_data_object(clean_lc, target_id, n_raw)
        # Cache yalnızca temizlenmiş standart veri nesnesini tutar; ham
        # Lightkurve nesnesine bağlı kalmadığı için sonraki çalıştırmalarda
        # Lightkurve import edilemese bile cache okunabilir.
        self._store_cached_data(cache_id, data)
        actual_cache_id = self._cache_identifier(
            target_id,
            data.sector,
            sigma_upper=sigma_upper,
            sigma_lower=sigma_lower,
        )
        if actual_cache_id != cache_id:
            self._store_cached_data(actual_cache_id, data)

        logger.info(
            f"Light curve hazır — {target_id} sektör {data.sector}: "
            f"{data.n_points_clean} temiz nokta, "
            f"tamlık: {data.completeness:.1%}"
        )

        return data

    def get_all_sectors(
        self,
        target: str | int,
        sigma_upper: float = 5.0,
        sigma_lower: float = 5.0,
    ) -> TESSMultiSectorData:
        """
        Tüm mevcut sektörler için TESS light curve verilerini alır.

        Parameters
        ----------
        target : str veya int
            TIC ID veya hedef adı.
        sigma_upper : float
            Üst aykırı değer eşiği.
        sigma_lower : float
            Alt aykırı değer eşiği.

        Returns
        -------
        TESSMultiSectorData
            Tüm sektörleri kapsayan çoklu light curve verisi.

        Örnekler
        --------
        >>> client = TESSClient()
        >>> multi = client.get_all_sectors("TIC 261136679")
        >>> print(f"{multi.n_sectors} sektör bulundu")
        """

        target_id = normalize_tic_id(target) if isinstance(target, (int, str)) else str(target)

        logger.info(f"Tüm sektörler aranıyor — hedef: {target_id}")

        # Tüm sektörleri ara
        search_result = self.search(target_id, sector=None)

        multi_data = TESSMultiSectorData(target_id=target_id)

        for i in range(len(search_result)):
            row = None
            try:
                table = getattr(search_result, "table", None)
                if table is not None:
                    row = table[i]
            except (IndexError, TypeError):
                row = None

            row_sector = self._sector_from_row(row)
            row_cache_id = (
                self._cache_identifier(
                    target_id,
                    row_sector,
                    sigma_upper=sigma_upper,
                    sigma_lower=sigma_lower,
                )
                if row_sector is not None
                else None
            )

            try:
                sector_data = self._load_cached_data(row_cache_id) if row_cache_id else None
                if sector_data is None:
                    raw_lc = self.download_lightcurve(search_result, index=i)
                    n_raw = len(raw_lc.time)

                    clean_lc = self._clean_lightcurve(
                        raw_lc,
                        sigma_upper=sigma_upper,
                        sigma_lower=sigma_lower,
                    )
                    sector_data = self._to_data_object(clean_lc, target_id, n_raw)
                    self._store_cached_data(
                        self._cache_identifier(
                            target_id,
                            sector_data.sector,
                            sigma_upper=sigma_upper,
                            sigma_lower=sigma_lower,
                        ),
                        sector_data,
                    )

                # Minimum veri kontrolü
                if sector_data.n_points_clean < 100:
                    logger.warning(
                        f"Sektör {sector_data.sector}: "
                        f"çok az veri ({sector_data.n_points_clean} nokta), atlanıyor."
                    )
                    continue

                multi_data.sectors.append(sector_data)

                logger.info(
                    f"Sektör {sector_data.sector} eklendi — "
                    f"{sector_data.n_points_clean} nokta"
                )

            except TESSDataError as e:
                logger.warning(f"Sektör {i} işlenemedi: {e}")
                continue
            except Exception as e:
                logger.error(f"Sektör {i} beklenmeyen hata: {e}")
                continue

        if multi_data.n_sectors == 0:
            raise TESSNoDataError(
                f"'{target_id}' için işlenebilir TESS verisi bulunamadı."
            )

        logger.info(
            f"Tüm sektörler tamamlandı — "
            f"{target_id}: {multi_data.n_sectors} sektör, "
            f"{multi_data.total_points} toplam nokta"
        )

        return multi_data

    def get_available_sectors(self, target: str | int) -> list[int]:
        """
        Hedef için mevcut TESS sektörlerini listeler (indirme yapmadan).

        Parameters
        ----------
        target : str veya int
            TIC ID veya hedef adı.

        Returns
        -------
        list[int]
            Mevcut sektör numaraları.
        """

        target_id = normalize_tic_id(target) if isinstance(target, (int, str)) else str(target)

        try:
            search_result = self.search(target_id, sector=None)
        except TESSNoDataError:
            return []

        sectors = []
        for row in getattr(search_result, "table", []):
            sector_num = self._sector_from_row(row)
            if sector_num is not None:
                sectors.append(sector_num)

        sectors = sorted(set(sectors))
        logger.info(f"{target_id}: {len(sectors)} sektör mevcut — {sectors}")

        return sectors