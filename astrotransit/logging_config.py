"""
Merkezi log yönetimi.

Loguru kullanarak tüm modüller için tutarlı loglama sağlar.
"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_level: str = "INFO", log_dir: str | Path | None = None) -> None:
    """
    Proje genelinde loglama yapılandırmasını kurar.

    Parameters
    ----------
    log_level : str
        Log seviyesi. DEBUG, INFO, WARNING, ERROR, CRITICAL.
    log_dir : str veya Path, opsiyonel
        Log dosyasının yazılacağı dizin.
        Verilmezse sadece konsola yazılır.
    """

    # Mevcut handler'ları temizle
    logger.remove()

    # Konsol çıktısı
    log_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stderr,
        format=log_format,
        level=log_level.upper(),
        colorize=True,
    )

    # Dosya çıktısı (istenirse)
    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_path / "astrotransit_{time:YYYY-MM-DD}.log",
            format=log_format,
            level="DEBUG",       # dosyaya her şeyi yaz
            rotation="10 MB",    # 10 MB'da yeni dosya
            retention="30 days", # 30 gün tut
            compression="zip",   # eski logları sıkıştır
            enqueue=True,        # thread-safe
        )

    logger.info(f"Loglama başlatıldı — seviye: {log_level}")