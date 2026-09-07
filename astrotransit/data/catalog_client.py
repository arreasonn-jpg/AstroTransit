"""
Katalog erişim istemcisi.

Gaia, SIMBAD, VizieR ve NASA Exoplanet Archive verilerine erişim sağlar.
Yıldız özelliklerinin doğrulanması ve çapraz eşleştirme için kullanılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from astroquery.simbad import Simbad
from astropy.table import Table
from loguru import logger

from astrotransit.data.mast_client import MASTClient, MASTQueryError
from astrotransit.utils.identifiers import extract_tic_number


@dataclass
class StellarProperties:
    """
    Yıldız fiziksel özellikleri.

    Attributes
    ----------
    tic_id : int
        TIC numarası.
    ra : float
        Rektasansiyon (derece).
    dec : float
        Deklinasyon (derece).
    teff : float
        Efektif sıcaklık (Kelvin).
    logg : float
        Yüzey çekim ivmesi (log cgs).
    radius : float
        Yıldız yarıçapı (güneş yarıçapı).
    mass : float
        Yıldız kütlesi (güneş kütlesi).
    tmag : float
        TESS büyüklüğü.
    distance : float
        Uzaklık (parsek).
    luminosity : float
        Işınım gücü (güneş luminositesi).
    metallicity : float
        Metallik ([Fe/H]).
    source : str
        Veri kaynağı (örn. "TIC", "Gaia", "SIMBAD").
    """

    tic_id: int = 0
    ra: float = 0.0
    dec: float = 0.0
    teff: float = 0.0
    logg: float = 0.0
    radius: float = 0.0
    mass: float = 0.0
    tmag: float = 0.0
    distance: float = 0.0
    luminosity: float = 0.0
    metallicity: float = 0.0
    source: str = ""
    extra: dict = field(default_factory=dict)

    def is_valid(self) -> bool:
        """Temel yıldız parametrelerinin mevcut olup olmadığını kontrol eder."""
        return self.teff > 0 and self.radius > 0

    def to_dict(self) -> dict:
        """Sözlük olarak döndürür."""
        return {
            "tic_id": self.tic_id,
            "ra": self.ra,
            "dec": self.dec,
            "teff": self.teff,
            "logg": self.logg,
            "radius_rsun": self.radius,
            "mass_msun": self.mass,
            "tmag": self.tmag,
            "distance_pc": self.distance,
            "luminosity_lsun": self.luminosity,
            "metallicity": self.metallicity,
            "source": self.source,
        }


class CatalogClient:
    """
    Katalog erişim istemcisi.

    TIC, Gaia ve SIMBAD kataloglarından yıldız özelliklerini sorgular.
    """

    def __init__(self):
        self._mast = MASTClient()
        logger.debug("CatalogClient başlatıldı.")

    def get_stellar_properties(self, tic_id: int | str) -> StellarProperties:
        """
        TIC kataloğundan yıldız özelliklerini alır.

        Parameters
        ----------
        tic_id : int veya str
            TIC numarası.

        Returns
        -------
        StellarProperties
            Yıldız fiziksel özellikleri.
        """

        if isinstance(tic_id, str):
            tic_id = extract_tic_number(tic_id)

        logger.info(f"Yıldız özellikleri sorgulanıyor: TIC {tic_id}")

        try:
            result = self._mast.query_tic_catalog(tic_id=tic_id)
        except MASTQueryError as e:
            logger.error(f"TIC katalog sorgusu başarısız: {e}")
            return StellarProperties(tic_id=tic_id, source="failed")

        if len(result) == 0:
            logger.warning(f"TIC {tic_id} için katalog verisi bulunamadı.")
            return StellarProperties(tic_id=tic_id, source="not_found")

        # En yakın eşleşmeyi al
        row = result[0]

        props = StellarProperties(
            tic_id=tic_id,
            ra=self._safe_float(row, 'ra'),
            dec=self._safe_float(row, 'dec'),
            teff=self._safe_float(row, 'Teff'),
            logg=self._safe_float(row, 'logg'),
            radius=self._safe_float(row, 'rad'),
            mass=self._safe_float(row, 'mass'),
            tmag=self._safe_float(row, 'Tmag'),
            distance=self._safe_float(row, 'd'),
            luminosity=self._safe_float(row, 'lum'),
            metallicity=self._safe_float(row, 'MH'),
            source="TIC",
        )

        if props.is_valid():
            logger.info(
                f"TIC {tic_id} — "
                f"Teff: {props.teff:.0f} K, "
                f"R: {props.radius:.2f} Rsun, "
                f"Tmag: {props.tmag:.2f}"
            )
        else:
            logger.warning(
                f"TIC {tic_id}: eksik yıldız parametreleri "
                f"(Teff: {props.teff}, R: {props.radius})"
            )

        return props

    def query_simbad(self, target_name: str) -> Optional[Table]:
        """
        SIMBAD veritabanında hedef sorgular.

        Parameters
        ----------
        target_name : str
            Hedef adı (örn. "TIC 261136679" veya "WASP-18").

        Returns
        -------
        Table veya None
            SIMBAD sonuçları.
        """

        logger.debug(f"SIMBAD sorgusu: {target_name}")

        try:
            custom_simbad = Simbad()
            custom_simbad.add_votable_fields(
                'flux(V)', 'sp', 'plx', 'rv_value', 'otype'
            )
            result = custom_simbad.query_object(target_name)

            if result is not None:
                logger.info(f"SIMBAD sonucu bulundu: {target_name}")
            else:
                logger.debug(f"SIMBAD'da bulunamadı: {target_name}")

            return result

        except Exception as e:
            logger.warning(f"SIMBAD sorgusu başarısız: {e}")
            return None

    @staticmethod
    def _safe_float(row, key: str, default: float = 0.0) -> float:
        """Tablo satırından güvenli float değeri çıkarır."""

        try:
            value = row[key]
            if value is None or (hasattr(value, 'mask') and value.mask):
                return default
            result = float(value)
            if not __import__('math').isfinite(result):
                return default
            return result
        except (KeyError, ValueError, TypeError):
            return default