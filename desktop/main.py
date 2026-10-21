"""Masaüstü uygulama giriş noktası.

Kullanım:
    python -m pip install -e ".[gui]"
    astrotransit-desktop [seçenekler]
Seçenekler:
    --smoke : pencereyi açıp 300 ms sonra kapatır; CI/exe doğrulaması için

Açılış sırası: QApplication → tema → açılış ekranı (splash) → ağır importer
(desktop.app, astrotransit zincirini çeker) → pencere. Böylece one-file
paketinde PySide6/astrotransit import süresi splash arkasında geçer.
"""

from __future__ import annotations

import sys


def main() -> None:
    """Uygulamayı başlatır; PySide6 eksikse açıklayıcı hata verir."""

    smoke = "--smoke" in sys.argv[1:]

    try:
        import PySide6  # noqa: F401 kontrol amaçlı import
    except ImportError as exc:
        raise SystemExit(
            "PySide6 bulunamadı. Masaüstü uygulaması için:\n"
            '  python -m pip install -e ".[gui]"\n'
            "Ardından: astrotransit-desktop"
        ) from exc

    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QApplication, QSplashScreen

    from desktop.theme import apply_theme

    app = QApplication.instance() or QApplication(["astrotransit-desktop"])
    apply_theme(app)

    # Splash: masa üstünde ilk görsel temas (ağır importlar bundan sonra).
    splash = None
    if not smoke:
        try:
            from desktop.branding import app_icon, splash_pixmap

            app.setWindowIcon(app_icon())
            splash = QSplashScreen(splash_pixmap())
            splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            splash.show()
            app.processEvents()
            splash.showMessage(
                "Modüller yükleniyor…", 0x80, "#e8eeff"
            )
            app.processEvents()
        except Exception:
            splash = None

    from desktop.app import MainWindow  # ağır zincir: splash görünürken yüklenir

    window = MainWindow()
    if splash is not None:
        window.setWindowIcon(app_icon())
        window.show()
        splash.finish(window)
    else:
        window.show()
    if smoke:
        QTimer.singleShot(300, app.quit)
    app.exec()


if __name__ == "__main__":
    main()
