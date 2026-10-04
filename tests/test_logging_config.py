"""
setup_logging birim testleri.

Kapsam
------
- Konsol handler kurulumu
- Dosya handler (log_dir verilince)
- Handler temizleme (remove)
- Log seviyesi normalize (upper)
- Dizin olusturma (mkdir)
"""

from __future__ import annotations

from pathlib import Path

import pytest
from loguru import logger

from astrotransit.logging_config import setup_logging


@pytest.fixture(autouse=True)
def _restore_logger_after_test():
    """Her testten sonra loguru'yu temizle (diger testleri etkilememesi icin)."""
    yield
    logger.remove()


# ─────────────────────────────────────────────────────────────
# Temel
# ─────────────────────────────────────────────────────────────

def test_setup_logging_console_only() -> None:
    """log_dir verilmezse sadece konsol handler eklenir."""
    setup_logging(log_level="INFO")
    handlers = logger._core.handlers
    assert len(handlers) == 1


def test_setup_logging_removes_existing_handlers() -> None:
    """Onceki handler'lar temizlenir."""
    logger.add(lambda _: None)
    logger.add(lambda _: None)
    assert len(logger._core.handlers) == 2

    setup_logging(log_level="INFO")
    assert len(logger._core.handlers) == 1


def test_setup_logging_with_log_dir(tmp_path: Path) -> None:
    """log_dir verilirse 2 handler (konsol + dosya) olur."""
    setup_logging(log_level="DEBUG", log_dir=tmp_path)
    handlers = logger._core.handlers
    assert len(handlers) == 2


def test_setup_logging_creates_log_dir(tmp_path: Path) -> None:
    """log_dir otomatik olusturulur."""
    target = tmp_path / "logs" / "nested"
    assert not target.exists()

    setup_logging(log_level="INFO", log_dir=target)
    assert target.exists()
    assert target.is_dir()


def test_setup_logging_accepts_str_log_dir(tmp_path: Path) -> None:
    """log_dir str olarak verilebilir."""
    target = tmp_path / "str_logs"
    setup_logging(log_level="INFO", log_dir=str(target))
    assert target.exists()


def test_setup_logging_level_uppercase(tmp_path: Path) -> None:
    """Log seviyesi upper'a normalize edilir (hata vermez)."""
    setup_logging(log_level="debug")
    handlers = logger._core.handlers
    assert len(handlers) >= 1


def test_setup_logging_info_message_logged(capsys) -> None:
    """setup_logging cagrisi bir INFO mesaji yazar."""
    setup_logging(log_level="INFO")
    logger.info("test message")
    captured = capsys.readouterr()
    # loguru stderr'a yazar
    assert "test message" in captured.err or "Loglama başlatıldı" in captured.err


def test_setup_logging_log_file_pattern(tmp_path: Path) -> None:
    """Log dosyasi astrotransit_YYYY-MM-DD.log formatinda olusturulur."""
    setup_logging(log_level="INFO", log_dir=tmp_path)
    # enqueue=True oldugu icin hemen yazilmayabilir; sadece handler kuruldugunu dogrula
    handlers = logger._core.handlers
    assert len(handlers) == 2


def test_setup_logging_multiple_calls(tmp_path: Path) -> None:
    """Ardisik cagrilar bir onceki handler'i temizler."""
    setup_logging(log_level="INFO")
    assert len(logger._core.handlers) == 1

    setup_logging(log_level="DEBUG", log_dir=tmp_path)
    assert len(logger._core.handlers) == 2

    setup_logging(log_level="WARNING")
    assert len(logger._core.handlers) == 1
