"""AstroTransit görsel kimlik: programatik logo / açılış ekranı.

Dış görsel dosyası YOK — her şey QPainter ile çizilir; bu sayede
PyInstaller paketinde kaynak toplama riski olmaz (coverage dışıdır,
pyproject omit).

Görsel dil: koyu uzay zemini + vurgu yörünge + "transit çukuru" imzası.
"""

from __future__ import annotations

import math
import random
from typing import Any

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from desktop.theme import ACCENT, BG, OK, TEXT, TEXT_DIM


def brand_pixmap(size: int = 256) -> QPixmap:
    """Kare uygulama logosu: uzay zemini + yörünge + transit çukuru."""

    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(BG))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    _space_background(painter, size, stars=int(size / 3))
    _orbit_mark(painter, size)
    _draw_transit_curve(painter, size, curve_top=int(size * 0.82))
    painter.end()
    return pixmap


def splash_pixmap(width: int = 560, height: int = 340) -> QPixmap:
    """Açılış ekranı: logo + isim + sürüm + mission satırı."""

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(BG))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    _space_background(painter, width, stars=90)
    _orbit_mark(painter, int(min(width, height) * 0.62))
    _draw_transit_curve(painter, width, curve_top=int(height * 0.80))

    title_rect = QRectF(0, height * 0.28, width, height * 0.20)
    font = QFont("Segoe UI")
    font.setPixelSize(int(height * 0.115))
    font.setBold(True)
    font.setLetterSpacing(QFont.AbsoluteSpacing, 3.0)
    painter.setFont(font)
    painter.setPen(QColor(TEXT))
    painter.drawText(title_rect, Qt.AlignHCenter | Qt.AlignVCenter, "ASTROTRANSIT")

    subtitle_rect = QRectF(0, height * 0.50, width, height * 0.09)
    sub_font = QFont("Segoe UI")
    sub_font.setPixelSize(int(height * 0.052))
    painter.setFont(sub_font)
    painter.setPen(QColor(TEXT_DIM))
    painter.drawText(
        subtitle_rect, Qt.AlignHCenter | Qt.AlignVCenter, "TESS Transit Keşif Konsolu"
    )

    mission_rect = QRectF(0, height * 0.62, width, height * 0.08)
    painter.drawText(
        mission_rect, Qt.AlignHCenter | Qt.AlignVCenter, "Örtük transit keşif • TESS SPOC"
    )
    painter.end()
    return pixmap


def app_icon() -> Any:
    """Pencere/taskbar ikonu (QIcon)."""

    from PySide6.QtGui import QIcon

    return QIcon(brand_pixmap(256))


def _space_background(painter: QPainter, side: int, stars: int = 80) -> None:
    """Dikey degrade + deterministik yıldız alanı (kod kontrollü, dosyasız)."""

    gradient = QLinearGradient(0.0, 0.0, side * 0.35, float(side))
    gradient.setColorAt(0.0, QColor("#0d1330"))
    gradient.setColorAt(0.55, QColor(BG))
    gradient.setColorAt(1.0, QColor("#101a3d"))
    painter.fillRect(0, 0, side, side, QBrush(gradient))

    rng = random.Random(20241021)  # deterministik: her koşumda aynı gökyüzü
    dot = QColor("#cdd9ff")
    for _ in range(stars):
        x = rng.uniform(0, side)
        y = rng.uniform(0, side)
        radius = rng.uniform(0.4, 1.6)
        dot.setAlpha(rng.randint(40, 190))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(dot))
        painter.drawEllipse(QRectF(x, y, radius, radius))


def _orbit_mark(painter: QPainter, side: int) -> None:
    """Vurgu yörünge halkası + gezegen noktası (üst köşe imza)."""

    center_x = side * 0.80
    center_y = side * 0.22
    radius = side * 0.155

    pen = QPen(QColor(ACCENT))
    pen.setWidthF(max(1.5, side * 0.010))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(
        QRectF(center_x - radius, center_y - radius, 2 * radius, 2 * radius)
    )

    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor(OK)))
    dot_r = side * 0.030
    painter.drawEllipse(
        QRectF(center_x - dot_r + radius * 20 / 45.0, center_y + dot_r / 2, 2 * dot_r, 2 * dot_r)
    )


def _draw_transit_curve(
    painter: QPainter, width: int, curve_top: int, amplitude: int = 0
) -> None:
    """Alt bantta 'geçiş çukuru' imzası: cos² profilli tek dip."""

    curve_h = max(18, int(width * 0.045))
    base_y = float(curve_top)
    dip_center = width * 0.62
    dip_half = width * 0.085
    depth = curve_h * 1.15

    path = QPainterPath()
    path.moveTo(0.0, base_y)
    steps = 200
    for step in range(steps + 1):
        x = width * step / steps
        dx = abs(x - dip_center)
        y = base_y + depth * (
            math.cos(math.pi * dx / (2 * dip_half)) ** 2 if dx < dip_half else 0.0
        )
        path.lineTo(x, y)
    path.lineTo(float(width), base_y)

    pen = QPen(QColor(ACCENT))
    pen.setWidthF(max(1.5, width * 0.004))
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

def build_window_icon(app: Any) -> None:
    """QApplication pencere ikonunu marka pixmap'ine ayarlar."""

    app.setWindowIcon(app_icon())
