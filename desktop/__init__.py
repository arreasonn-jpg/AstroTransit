"""AstroTransit Masaüstü Uygulaması (PySide6).

Kod modülleri:
- helpers  : saf yardımcı fonksiyonlar (Qt yok, test edilebilir)
- analysis : Qt-bağımsız pipeline çalıştırma katmanı
- worker   : QThread sarmalayıcı (UI tarafı)
- app/main: ana pencere ve giriş noktası (UI tarafı)

GUI bağımlılığı isteğe bağlıdır: `python -m pip install -e ".[gui]"`
"""

from astrotransit.version import __version__

__all__ = ["__version__"]
