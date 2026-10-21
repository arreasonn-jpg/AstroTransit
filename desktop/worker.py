"""QThread tabanlı analiz ve keşif worker'ları (UI katmanı)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Optional

from PySide6.QtCore import QThread, Signal

from desktop.analysis import AnalysisConfig, analyze_targets
from desktop.discovery import discover_targets


class DiscoveryWorker(QThread):
    """MAST keşfi + ardıl analizi tek akışta çalıştırır.

    İlk ``count`` hedef keşfedilir (log + tek seferlik ilerleme sinyali),
    sonra keşfedilen hedef listesiyle ``analyze_targets`` koşulur; ilerleme
    sinyalleri birebir ``AnalysisWorker`` ile aynı anlamlıdır.
    """

    log_line = Signal(str)
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        count: int,
        base: AnalysisConfig,
        *,
        seed: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.count = count
        self.base = base
        self.seed = seed

    def run(self) -> None:
        try:
            targets = discover_targets(self.count, seed=self.seed, log_sink=self.log_line.emit)
            self.progress.emit(0, self.count, f"keşif: {len(targets)} hedef seçildi")
            config = replace(self.base, targets=targets)
            results = analyze_targets(
                config,
                log_sink=self.log_line.emit,
                progress=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(results)



class AnalysisWorker(QThread):
    """Pipeline'ı arka planda çalıştırır; sinyallerle UI'ya iletir."""

    log_line = Signal(str)
    progress = Signal(int, int, str)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, config: AnalysisConfig, parent=None) -> None:
        super().__init__(parent)
        self.config = config

    def run(self) -> None:
        try:
            results = analyze_targets(
                self.config,
                log_sink=self.log_line.emit,
                progress=self.progress.emit,
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished_ok.emit(results)

    @staticmethod
    def summarize(results: list[Any]) -> str:
        """Sonucu bilgisayar-okur kısa özete çevirir."""

        n = len(results)
        successes = sum(1 for r in results if getattr(r, "success", False))
        confirmed = sum(int(getattr(r, "candidates_confirmed", 0) or 0) for r in results)
        return f"{n}/{successes} başarılı, {confirmed} onaylı aday"
