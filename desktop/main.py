"""Masaüstü uygulama giriş noktası.

Kullanım:
    python -m pip install -e ".[gui]"
    astrotransit-desktop [seçenekler]
Seçenekler:
    --smoke : pencereyi acip 300 ms sonra kapatır; CI/exe doğrulaması için
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
            'Ardından: astrotransit-desktop'
        ) from exc

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from desktop.app import MainWindow
    from desktop.theme import apply_theme

    app = QApplication.instance() or QApplication(["astrotransit-desktop"])
    apply_theme(app)
    window = MainWindow()
    window.show()
    if smoke:
        QTimer.singleShot(300, app.quit)
    app.exec()


if __name__ == "__main__":
    main()

