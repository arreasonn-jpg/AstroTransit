"""
MAST (Mikulski Archive for Space Telescopes) temel istemcisi.

MAST API ile bağlantı, sorgu ve hata yönetimi sağlar.
Hem TESS hem JWST istemcileri bu modülü temel alır.
"""

from __future__ import annotations

from typing import Optional

from astroquery.mast import Observations, Catalogs
from astropy.table import Table
from loguru import logger


class MASTConnectionError(Exception):
    """MAST bağlantı hatası."""
    pass


class MASTQueryError(Exception):
    """MAST sorgu hatası."""
    pass


class MASTClient:
    """
    MAST API temel istemcisi.

    MAST servislerine bağlantıyı yönetir ve ortak sorgu
    işlevlerini sağlar.

    Parameters
    ----------
    api_token : str, opsiyonel
        MAST API token. Verilmezse anonim erişim kullanılır.
    """

    def __init__(self, api_token: Optional[str] = None):
        self._authenticated = False

        if api_token:
            try:
                Observations.login(token=api_token)
                self._authenticated = True
                logger.info("MAST API kimlik doğrulaması başarılı.")
            except Exception as e:
                logger.warning(
                    f"MAST API kimlik doğrulaması başarısız: {e}. "
                    f"Anonim erişim kullanılacak."
                )
        else:
            logger.debug("MAST API anonim erişim modu.")

    @property
    def is_authenticated(self) -> bool:
        """Kimlik doğrulaması yapılmış mı."""
        return self._authenticated

    def query_observations(
        self,
        target_name: Optional[str] = None,
        coordinates: Optional[str] = None,
        radius: str = "0.02 deg",
        obs_collection: Optional[str] = None,
        dataproduct_type: Optional[str] = None,
        filters: Optional[dict] = None,
    ) -> Table:
        """
        MAST'ta gözlem sorgusu yapar.

        Parameters
        ----------
        target_name : str, opsiyonel
            Hedef adı (örn. "TIC 123456789").
        coordinates : str, opsiyonel
            Koordinatlar (örn. "350.25 -20.11").
        radius : str
            Arama yarıçapı.
        obs_collection : str, opsiyonel
            Gözlem koleksiyonu (örn. "TESS", "JWST").
        dataproduct_type : str, opsiyonel
            Veri ürün tipi (örn. "timeseries").
        filters : dict, opsiyonel
            Ek filtre parametreleri.

        Returns
        -------
        Table
            Sorgu sonuçları.

        Raises
        ------
        MASTQueryError
            Sorgu başarısız olursa.
        """

        query_params = {}

        if target_name:
            query_params["objectname"] = target_name
        if coordinates:
            query_params["coordinates"] = coordinates
        if radius:
            query_params["radius"] = radius
        if obs_collection:
            query_params["obs_collection"] = obs_collection
        if dataproduct_type:
            query_params["dataproduct_type"] = dataproduct_type

        # Ek filtreler
        if filters:
            query_params.update(filters)

        logger.debug(f"MAST sorgusu: {query_params}")

        try:
            if target_name and not coordinates:
                results = Observations.query_object(
                    target_name,
                    radius=radius,
                )
            else:
                results = Observations.query_criteria(**query_params)

            # Koleksiyon filtresi uygula (query_criteria dışında kalan durumlar için)
            if obs_collection and len(results) > 0:
                mask = results["obs_collection"] == obs_collection
                results = results[mask]

            if dataproduct_type and len(results) > 0:
                mask = results["dataproduct_type"] == dataproduct_type
                results = results[mask]

            logger.info(f"MAST sorgusu tamamlandı: {len(results)} sonuç bulundu.")
            return results

        except Exception as e:
            raise MASTQueryError(f"MAST sorgusu başarısız: {e}") from e

    def get_product_list(self, observations: Table) -> Table:
        """
        Gözlemler için indirilebilir veri ürünlerini listeler.

        Parameters
        ----------
        observations : Table
            MAST gözlem tablosu.

        Returns
        -------
        Table
            Veri ürünleri listesi.
        """

        if len(observations) == 0:
            logger.warning("Boş gözlem tablosu, ürün listesi alınamıyor.")
            return Table()

        try:
            products = Observations.get_product_list(observations)
            logger.debug(f"Ürün listesi alındı: {len(products)} ürün.")
            return products

        except Exception as e:
            raise MASTQueryError(f"Ürün listesi alınamadı: {e}") from e

    def query_tic_catalog(
        self,
        tic_id: Optional[int] = None,
        coordinates: Optional[str] = None,
        radius: str = "0.02 deg",
    ) -> Table:
        """
        TESS Input Catalog (TIC) sorgusu yapar.

        Parameters
        ----------
        tic_id : int, opsiyonel
            TIC numarası.
        coordinates : str, opsiyonel
            Koordinatlar.
        radius : str
            Arama yarıçapı.

        Returns
        -------
        Table
            TIC katalog sonuçları.
        """

        import time as _time

        last_error = None
        for attempt in range(3):
            try:
                if tic_id is not None:
                    results = Catalogs.query_object(
                        f"TIC {tic_id}",
                        catalog="TIC",
                        radius=radius,
                    )
                elif coordinates is not None:
                    results = Catalogs.query_region(
                        coordinates,
                        catalog="TIC",
                        radius=radius,
                    )
                else:
                    raise ValueError("tic_id veya coordinates parametrelerinden biri gereklidir.")

                logger.info(f"TIC kataloğu sorgulandı: {len(results)} sonuç.")
                return results

            except Exception as e:
                last_error = e
                wait = 2 ** attempt  # 1, 2, 4 saniye
                if attempt < 2:
                    logger.warning(
                        f"TIC katalog denemesi {attempt+1}/3 basarisiz: {e}. "
                        f"{wait}s bekleyip tekrar denenecek..."
                    )
                    _time.sleep(wait)
                else:
                    logger.error(f"TIC katalog 3 deneme sonrasi basarisiz: {e}")

        raise MASTQueryError(f"TIC katalog sorgusu başarısız: {last_error}") from last_error