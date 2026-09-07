"""Pipeline çıktı yöneticisi."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from loguru import logger

from astrotransit.outputs.csv_export import CSVExporter
from astrotransit.outputs.json_writer import JSONWriter
from astrotransit.outputs.parquet_writer import ParquetWriter
from astrotransit.outputs.schemas import (
    TransitCandidateRecord,
    build_long_period_record,
    build_record,
)
from astrotransit.settings import Settings, get_settings
from astrotransit.utils.paths import ProjectPaths


class OutputManager:
    """JSON + Parquet kayıtlarını aynı şemadan yöneten sınıf.

    ``OutputManager`` tek bir orchestrator içinde birden fazla TESS hedefi
    tarafından paylaşılabilir. ``close`` idempotent'tır ve ``flush`` kayıtları
    kapatmadan diske taşır; bu, batch çalıştırmalarında önceki kayıtların
    kaybolmasını engeller.
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        *,
        output_dir: str | Path | None = None,
        parquet_batch_size: int = 100,
    ):
        self.settings = settings or get_settings()
        configured_output = output_dir if output_dir is not None else self.settings.general.output_dir
        self.paths = ProjectPaths(
            output_dir=str(configured_output),
            temp_dir=self.settings.general.temp_dir,
        )
        self.earth_similarity_profile = getattr(
            self.settings.quality,
            "earth_similarity_profile",
            "photometric_earth_analog",
        )
        self.json_writer = JSONWriter(self.paths.json)
        self.parquet_writer = ParquetWriter(
            self.paths.parquet,
            filename="astrotransit_candidates.parquet",
            batch_size=parquet_batch_size,
        )
        self.csv_exporter = CSVExporter(self.paths.csv)
        self._records: list[TransitCandidateRecord] = []
        self._closed = False

    @property
    def records(self) -> list[TransitCandidateRecord]:
        return list(self._records)

    @property
    def parquet_path(self) -> Path:
        return self.parquet_writer.path

    def write(
        self,
        candidate: Any,
        quality_result: Any = None,
        fit_result: Any = None,
        stellar_props: Any = None,
        followup_result: Any = None,
    ) -> TransitCandidateRecord:
        """Bir pipeline sonucunu JSON ve Parquet'e yazar."""

        if self._closed:
            raise RuntimeError("Kapatılmış OutputManager tekrar kullanılamaz.")

        record = build_record(
            candidate=candidate,
            quality_result=quality_result,
            fit_result=fit_result,
            stellar_props=stellar_props,
            followup_result=followup_result,
            figure_dir=str(self.paths.target_figure_dir(str(getattr(candidate, "target_id", "target")))),
            earth_similarity_profile=self.earth_similarity_profile,
        )
        json_path = self.json_writer.write_candidate(record)
        record.json_path = str(json_path)
        # JSONWriter payload'a gerçek yolu kendisi yazdı; Parquet kaydında da
        # aynı provenance bilgisini tutuyoruz.
        self.parquet_writer.append(record)
        self._records.append(record)
        return record

    def write_long_period(
        self,
        long_period_result: Any,
        stellar_props: Any = None,
    ) -> Optional[TransitCandidateRecord]:
        """Uzun periyot screening kaydını JSON/Parquet'e yazar."""

        if self._closed:
            raise RuntimeError("Kapatılmış OutputManager tekrar kullanılamaz.")
        record = build_long_period_record(
            long_period_result,
            stellar_props=stellar_props,
            earth_similarity_profile=self.earth_similarity_profile,
        )
        if record is None:
            return None
        json_path = self.json_writer.write_candidate(record)
        record.json_path = str(json_path)
        self.parquet_writer.append(record)
        self._records.append(record)
        return record

    def append(self, record: TransitCandidateRecord) -> TransitCandidateRecord:
        """Önceden oluşturulmuş kaydı çıktı katmanına ekler."""

        if self._closed:
            raise RuntimeError("Kapatılmış OutputManager tekrar kullanılamaz.")
        if not isinstance(record, TransitCandidateRecord):
            raise TypeError("record TransitCandidateRecord olmalıdır.")
        json_path = self.json_writer.write_candidate(record)
        record.json_path = str(json_path)
        self.parquet_writer.append(record)
        self._records.append(record)
        return record

    def flush(self) -> None:
        """Buffer'ları diske yazar; yöneticiyi kapatmaz."""

        if not self._closed:
            self.parquet_writer.flush()

    def export_csv(self, filename: str = "astrotransit_candidates.csv") -> Path:
        """Mevcut Parquet veya bellekteki kayıtları CSV'ye aktarır."""

        self.flush()

        # PyArrow ParquetWriter footer'ı yalnızca close() sırasında yazar.
        # Açık bir writer'ın dosyasını okumaya çalışmak, geçici/eksik footer
        # nedeniyle hata verir. Manager açıkken aynı kayıt kaynağından CSV
        # üret; manager kapalıysa tamamlanmış Parquet'i tercih et.
        dataframe = None
        if self._closed and self.parquet_path.exists():
            try:
                dataframe = ParquetWriter.read(self.parquet_path)
            except Exception as exc:
                logger.warning(f"Parquet CSV'ye okunamadı: {exc}")

        if dataframe is None:
            try:
                import pandas as pd
            except ImportError as exc:  # pragma: no cover
                raise ImportError("CSV çıktısı için 'pandas' gereklidir.") from exc
            dataframe = pd.DataFrame([record.to_flat_dict() for record in self._records])

        return self.csv_exporter.export_summary(dataframe, filename=filename)

    def close(self) -> None:
        """Kalan kayıtları yazar ve tüm kaynakları kapatır."""

        if self._closed:
            return
        self.parquet_writer.close()
        self._closed = True
        logger.info(f"Çıktı yöneticisi kapatıldı — {len(self._records)} kayıt")

    def __enter__(self) -> "OutputManager":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
