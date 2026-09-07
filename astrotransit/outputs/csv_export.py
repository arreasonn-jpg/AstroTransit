"""CSV dışa aktarma yardımcıları."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from loguru import logger

from astrotransit.outputs.schemas import TransitCandidateRecord


class CSVExporter:
    """Düz aday kayıtlarını veya DataFrame'leri CSV'ye aktarır."""

    def __init__(self, output_dir: str | Path, filename: str = "astrotransit_candidates.csv"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.filename = filename

    def export_summary(self, data, filename: str | None = None) -> Path:
        """DataFrame'i CSV'ye yazar."""

        try:
            import pandas as pd  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            raise ImportError("CSV çıktısı için 'pandas' gereklidir.") from exc

        if not hasattr(data, "to_csv"):
            raise TypeError("data pandas.DataFrame benzeri to_csv() nesnesi olmalıdır.")
        path = self.output_dir / (filename or self.filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        data.to_csv(path, index=False)
        logger.info(f"CSV özeti yazıldı: {path}")
        return path

    def export_records(
        self,
        records: Iterable[TransitCandidateRecord],
        filename: str | None = None,
    ) -> Path:
        """Transit kayıtlarını CSV'ye aktarır."""

        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover
            raise ImportError("CSV çıktısı için 'pandas' gereklidir.") from exc
        rows = [record.to_flat_dict() if isinstance(record, TransitCandidateRecord) else dict(record) for record in records]
        return self.export_summary(pd.DataFrame(rows), filename=filename)
