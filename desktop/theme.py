"""AstroTransit masaüstü teması: koyu uzay-konsolu paleti + genel QSS.

UI katmanı olduğu için coverage dışıdır (pyproject omit). Palet tek yerden
yönetilir; QSS seçicileri PySide6'nın desteklediği alt kümede kalır.

v2 (profesyonel restorasyon): kenar çubuğu navigasyonu, durum çipleri,
metrik kartları, ince ayar kaydırma çubukları, açılır ipuçları ve
odak/etkin durumlarda vurgu.
"""

from __future__ import annotations

from typing import Any

# ── Palet ────────────────────────────────────────────────────────────────
BG = "#0a0f1e"          # pencere zemini
SIDE = "#070b16"        # kenar çubuğu zemini (daha derin)
PANEL = "#121a2f"       # kart / form zemini
PANEL_2 = "#19223d"     # giriş alanı zemini
PANEL_3 = "#222e52"     # hover yükselmesi
BORDER = "#28334f"      # kenarlık
TEXT = "#e8eeff"        # ana metin
TEXT_DIM = "#8a96b8"    # ikincil metin
ACCENT = "#5f8dff"      # vurgu (buton / ilerleme / aktif nav)
ACCENT_SOFT = "rgba(95, 141, 255, 15%)"  # yarı saydam vurgu dolgusu (QSS rgba)
ACCENT_HOVER = "#7ba0ff"
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
    QMainWindow, QDialog {{
        background: {BG};
        border: none;
    }}
    QLabel {{
        background: transparent;
        color: {TEXT};
    }}
    QLabel#appTitle {{
        font-size: 23px;
        font-weight: 800;
        letter-spacing: 3px;
        color: {TEXT};
    }}
    QLabel#brandMini {{
        font-size: 15px;
        font-weight: 700;
        letter-spacing: 2px;
        color: {TEXT};
    }}
    QLabel#appSubtitle {{
        color: {TEXT_DIM};
        font-size: 12px;
    }}
    QLabel#fieldLabel {{
        color: {TEXT_DIM};
        font-weight: 600;
        background: transparent;
    }}
    QLabel#pageHeader {{
        font-size: 19px;
        font-weight: 700;
        background: transparent;
    }}
    QLabel#pageHint {{
        color: {TEXT_DIM};
        font-size: 12px;
        background: transparent;
    }}

    /* ── Kenar çubuğu ── */
    QWidget#sidebar {{
        background: {SIDE};
        border-right: 1px solid {BORDER};
    }}
    QPushButton#navBtn, QToolButton#navBtn {{
        background: transparent;
        color: {TEXT_DIM};
        border: none;
        border-radius: 8px;
        text-align: left;
        padding: 10px 14px;
        font-weight: 600;
        font-size: 13.5px;
    }}
    QPushButton#navBtn:hover, QToolButton#navBtn:hover {{
        background: {PANEL};
        color: {TEXT};
    }}
    QPushButton#navBtn:checked, QToolButton#navBtn:checked {{
        background: {ACCENT_SOFT};
        color: {TEXT};
        border-left: 3px solid {ACCENT};
        border-radius: 8px;
        padding-left: 11px;
    }}
    QLabel#sideDivider {{
        border-top: none;
    }}

    /* ── Durum çipleri ── */
    QFrame#chip {{
        border-radius: 11px;
        padding: 3px 12px;
        font-weight: 700;
        font-size: 12px;
        border: none;
    }}
    QFrame#chip[chipTone="info"] {{ background: {ACCENT_SOFT}; color: {ACCENT_HOVER}; }}
    QFrame#chip[chipTone="ok"]   {{ background: rgba(61, 220, 151, 16%); color: {OK}; }}
    QFrame#chip[chipTone="warn"] {{ background: rgba(255, 180, 84, 16%); color: {WARN}; }}
    QFrame#chip[chipTone="danger"] {{ background: rgba(255, 107, 107, 16%); color: {DANGER}; }}

    /* ── Metrik kartları ── */
    QFrame#card {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
    }}
    QLabel#metricTitle {{
        color: {TEXT_DIM};
        font-size: 11.5px;
        font-weight: 600;
        letter-spacing: 1px;
        background: transparent;
    }}
    QLabel#metricValue {{
        color: {TEXT};
        font-size: 24px;
        font-weight: 700;
        background: transparent;
    }}

    /* ── Girdiler ── */
    QLineEdit, QComboBox, QSpinBox {{
        background: {PANEL_2};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 7px 11px;
        min-height: 22px;
        selection-background-color: {ACCENT};
        selection-color: {TEXT};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{
        border: 1px solid {PANEL_3};
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
        border: 1px solid {ACCENT};
        background: {PANEL_3};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {TEXT_DIM};
        border-color: {BORDER};
        background: {BG};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 6px;
        selection-background-color: {ACCENT_PRESSED};
        padding: 4px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        background: {PANEL};
        border: none;
        width: 16px;
    }}

    /* ── Butonlar ── */
    QPushButton {{
        background: {ACCENT};
        color: #ffffff;
        font-weight: 700;
        border: none;
        border-radius: 8px;
        padding: 9px 20px;
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
        background: {PANEL_3};
    }}
    QPushButton#ghost {{
        background: transparent;
        color: {TEXT_DIM};
        border: none;
    }}
    QPushButton#ghost:hover {{
        color: {TEXT};
        background: {PANEL};
    }}

    /* ── Tablolar ── */
    QTableWidget {{
        background: {PANEL};
        alternate-background-color: {PANEL_2};
        border: 1px solid {BORDER};
        border-radius: 10px;
        gridline-color: {BORDER};
        selection-background-color: {ACCENT_PRESSED};
    }}
    QHeaderView::section {{
        background: {PANEL_2};
        color: {TEXT_DIM};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 9px 12px;
        font-weight: 700;
        font-size: 12px;
    }}
    QTableWidget::item {{
        padding: 5px 8px;
    }}
    QTableWidget::item:selected {{
        background: {ACCENT_PRESSED};
        color: {TEXT};
    }}

    /* ── İlerleme ── */
    QProgressBar {{
        background: {PANEL_2};
        border: 1px solid {BORDER};
        border-radius: 9px;
        text-align: center;
        color: {TEXT};
        min-height: 19px;
        font-weight: 600;
        font-size: 11.5px;
    }}
    QProgressBar::chunk {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT_PRESSED}, stop:1 {ACCENT_HOVER});
        border-radius: 8px;
    }}

    /* ── Onay kutusu ── */
    QCheckBox {{
        background: transparent;
        spacing: 8px;
    }}
    QCheckBox:hover {{
        color: {ACCENT_HOVER};
    }}
    QCheckBox::indicator {{
        width: 17px;
        height: 17px;
        border: 1px solid {BORDER};
        border-radius: 5px;
        background: {PANEL_2};
    }}
    QCheckBox::indicator:hover {{
        border-color: {ACCENT};
    }}
    QCheckBox::indicator:checked {{
        background: {ACCENT};
        border-color: {ACCENT};
    }}

    /* ── Konsol ── */
    QPlainTextEdit {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
        color: {TEXT};
        font-family: "Cascadia Mono", "Consolas", "JetBrains Mono", monospace;
        font-size: 12px;
        selection-background-color: {ACCENT_PRESSED};
    }}

    /* ── Kaydırma çubukları (ince ayar) ── */
    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {PANEL_3};
        border-radius: 4px;
        min-height: 28px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 9px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {PANEL_3};
        border-radius: 4px;
        min-width: 28px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {ACCENT};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}

    QSplitter::handle {{
        background: {BORDER};
        width: 2px;
    }}

    QGroupBox {{
        background: {PANEL};
        border: 1px solid {BORDER};
        border-radius: 10px;
        margin-top: 12px;
        padding: 15px 12px 11px 12px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 6px;
        color: {ACCENT_HOVER};
        background: transparent;
    }}

    QToolTip {{
        background: {PANEL_2};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 6px;
        padding: 6px 9px;
        font-size: 12px;
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
