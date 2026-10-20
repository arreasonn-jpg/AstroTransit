"""Qt-bağımsız analiz çalıştırma katmanı.

Orkestratörü çağırır, loguru loglarını geri çağrıya aktarır ve
hedef-bazlı ilerleme sinyali üretir. UI katmanı (QThread) bunu
 Qt sinyalleriyle sarmalar; birim testler Qt olmadan çalışabilir.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from loguru import logger


@dataclass
class AnalysisConfig:
    """Analiz çalıştırma yapılandırması."""

    targets: list[str] = field(default_factory=list)
    sectors: Optional[list[int]] = None
    force_map: bool = True
    force_mcmc: bool = False
    skip_visualization: bool = False
    skip_catalog: bool = False
    config_path: Optional[str] = None
    log_level: str = "INFO"


class AnalysisError(RuntimeError):
    """Pipeline kurulumu veya çalıştırma sırasında beklenmeyen hata."""


def _forward_log(log_sink: Optional[Callable[[str], None]]):
    """loguru sink'i log_sink callablerine çevirir (None ise None)."""

    if log_sink is None:
        return None

    def _handler(message) -> None:
        text = str(message)
        if text.endswith("\n"):
            text = text[:-1]
        try:
            log_sink(text)
        except Exception as e:  # pragma: no cover - UI katmanı koruması
            logger.warning(f"Log sink hatası: {e}")

    return _handler


def analyze_targets(
    config: AnalysisConfig,
    *,
    log_sink: Optional[Callable[[str], None]] = None,
    progress: Optional[Callable[[int, int, str], None]] = None,
) -> list[Any]:
    """Hedef listesini orkestratör üzerinden çalıştırır.

    Gerçek ilerleme: her hedef tamamlandığında ``progress(done, total,
    target_id)`` çağrılır. Sonuç: hedef bazlı ``TESSTargetResult`` listesi.

    Raises
    ------
    AnalysisError
        Hedef listesi boşsa veya pipeline kurulumu başarısızsa.
    """

    if not config.targets:
        raise AnalysisError("Analiz için hedef listesi boş.")

    sink = _forward_log(log_sink)
    sink_id: Optional[int] = None
    if sink is not None:
        sink_id = logger.add(
            sink,
            level="SUCCESS",
            colorize=False,
            backtrace=False,
            diagnose=False,
        )

    from astrotransit.pipelines.orchestrator import AstroTransitOrchestrator

    orchestrator = AstroTransitOrchestrator(
        config_path=config.config_path,
        force_map=config.force_map,
        force_mcmc=config.force_mcmc,
        skip_visualization=config.skip_visualization,
        skip_catalog=config.skip_catalog,
        log_level=config.log_level,
    )

    try:
        if len(config.targets) == 1:
            results = [
                orchestrator.run_single(config.targets[0], sectors=config.sectors)
            ]
            if progress is not None:
                progress(1, 1, config.targets[0])
        else:
            results = orchestrator.run_batch(
                list(config.targets),
                sectors=config.sectors,
                progress=progress,
            )
    except Exception as exc:
        raise AnalysisError(str(exc)) from exc
    finally:
        _close_quietly(orchestrator)
        if sink_id is not None:
            logger.remove(sink_id)

    return results


def _close_quietly(orchestrator: Any) -> None:
    """Orkestratör kapatma hatasını yutar (kapatma zaten opsiyonel)."""

    try:
        orchestrator.close()
    except Exception as e:  # pragma: no cover - UI katmanı koruması
        logger.warning(f"Orkestratör kapatma uyarısı: {e}")


def project_root() -> Path:
    """Proje kökünü ProjectPaths'ten alır (pay tekrarına dikkat)."""

    from astrotransit.utils.paths import ProjectPaths

    return ProjectPaths().root
