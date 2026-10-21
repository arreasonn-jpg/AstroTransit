"""AstroTransit masaüstü teması: koyu uzay-konsolu paleti + genel QSS.

UI katmanı olduğu için coverage dışıdır (pyproject omit). Palet tek yerden
yönetilir; QSS seçicileri PySide6'nın desteklediği alt kümede kalır.
"""

from __future__ import annotations

from typing import Any

# ── Palet ────────────────────────────────────────────────────────────────
BG = "#0b1020"          # pencere zemini
PANEL = "#131a2e"       # kart / form zemini
PANEL_2 = "#1a2340"     # giriş alanı zemini
BORDER = "#2a3554"      # kenarlık
TEXT = "#e6ecff"        # ana metin
TEXT_DIM = "#8a96b8"    # ikincil metin
ACCENT = "#5b8cff"      # vurgu (buton / ilerleme / sekme)
ACCENT_HOVER = "#6f9bff"
ACCENT_PRESSED = "#4a79e6"
OK = "#3ddc97"          # başarı
WARN = "#ffb454"        # uyarı
DANGER = "#ff6b6b"      # hata


def _qss() -> str:
    """Genel stil sayfası üretir."""

    return f"""
    QWidget {{
        background: {BG};
        color: {TEXT};
        font-family: "Segoe UI", "Inter", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QTabWidget::pane {{
        background: {BG};
        border: none;
    }}
    QLabel {{
        background: transparent;
        color: {TEXT};
    }}
    QLabel#appTitle {{
        font-size: 21px;
        font-weight: 700;
        letter-spacing: 1px;
    }}
    QLabel#appSubtitle {{
        color: {TEXT_DIM};
        font-size: 12px;
    }}
    QLabel#fieldLabel {{
        color: {TEXT_DIM};
        font-weight: 600;
    }}

    QTabBar::tab {{
        background: transparent;
        color: {TEXT_DIM};
        padding: 8px 18px;
        margin-right: 2px;
        border: none;
        border-bottom: 2px solid transparent;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        color: {TEXT};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover {{
        color: {TEXT};
    }}

    QLineEdit, QComboBox, QSpinBox {{
        background: {PANEL_2};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 10px;
        min-height: 22px;
        selection-background-color: {ACCENT};
        selection-color: {TEXT};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {ACCENT};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {TEXT_DIM};
        border-color: {BORDER};
        background: {BG};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        border: 1px solid {BORDER};
        selection-background-color: {ACCENT_PRESSED};
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: {PANEL};
        border: none;
        width: 16px;
    }}

    QPushButton {{
        background: {ACCENT};
        color: #ffffff;
        font-weight: 600;
        border: none;
        border-radius: 6px;
        padding: 8px 18px;
    }}
    QPushButton:hover {{
        background: {ACCENT_HOVER};
    }}
    QPushButton:pressed {{
        background: {ACCENT_PRESSED};
    }}
    QPushButton:disabled {{
        background: {BORDER};
        color: {TEXT_DIM};
    }}
    QPushButton#secondary {{
        background: {PANEL_2};
        color: {TEXT};
        border: 1px solid {BORDER};
    }}
    QPushButton#secondary:hover {{
        border: 1px solid {ACCENT};
        background: {PANEL_2};
    }}

    QTableWidget {{
        background: {PANEL};
        alternate-background-color: {PANEL_2};
        border: 1px solid {BORDER};
        border-radius: 6px;
        gridline-color: {BORDER};
    }}
    QHeaderView::section {{
        background: {PANEL_2};
        color: {TEXT_DIM};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 7px 10px;
        font-weight: 600;
    }}
    QTableWidget::item:selected {{
        background: {ACCENT_PRESSED};
        color: {TEXT};
    }}

    QProgressBar {{
        background: {PANEL_2};
        border: 1px solid {BORDER};
        border-radius: 6px;
        text-align: center;
        color: {TEXT};
        min-height: 16px;
    }}
    QProgressBar::chunk {{
        background: {ACCENT};
        border-radius: 5px;
    }}

    QCheckBox {{
        background: transparent;
        spacing: 7px;
    }}
    QCheckBox::indicator {{
        width: 16px;
        height: 16px;
        border: 1px solid {BORDER};
        border-radius: 4px;
        background: {PANEL_2};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    QPlainTextEdit {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 6px;
        color: {TEXT};
        font-family: "Consolas", "JetBrains Mono", monospace;
        font-size: 12px;
    }}

    QSplitter::handle {{
        background: {BORDER};
        width: 2px;
    }}

    QGroupBox {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 8px;
        margin-top: 12px;
        padding: 14px 12px 10px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 6px;
        color: {ACCENT};
        background: transparent;
    }}

    QStatusBar {{
        background: {PANEL};
        color: {TEXT_DIM};
        border-top: 1px solid {BORDER};
    }}
    """


def apply_theme(app: Any) -> None:
    """Stil sayfasını uygulamaya bağlar.

    ``app`` için QApplication kabul eder; PySide6 stub tipleri ile
    ``QApplication.instance()`` dönen "Application" tipi uyumludur.
    """

    app.setStyleSheet(_qss())
