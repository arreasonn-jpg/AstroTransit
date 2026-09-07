"""Pipeline çıktı yöneticisi."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import json
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
from astrotransit.science.earth_similarity import score_earth_similarity
from astrotransit.validation.followup import coerce_followup_result
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

    def find_record(
        self,
        source_id: str,
        sector: int,
    ) -> Optional[TransitCandidateRecord]:
        """Bellekteki veya mevcut Parquet kataloğundaki kaydı bulur."""

        source_id = str(source_id)
        sector = int(sector)
        for record in self._records:
            if record.source_id == source_id and record.sector == sector:
                return record

        rows = list(getattr(self.parquet_writer, "_existing_rows", []))
        rows.extend(getattr(self.parquet_writer, "_buffer", []))
        field_names = {item.name for item in fields(TransitCandidateRecord)}
        for row in rows:
            if str(row.get("source_id", "")) != source_id:
                continue
            try:
                if int(row.get("sector", -1)) != sector:
                    continue
            except (TypeError, ValueError):
                continue
            values = {name: row[name] for name in field_names if name in row}
            record = TransitCandidateRecord(**values)
            self._records.append(record)
            return record
        return None

    def update_followup(
        self,
        record: TransitCandidateRecord,
        followup_result: Any,
    ) -> TransitCandidateRecord:
        """Mevcut adaya doğrulanmış takip kanıtını bağlar ve upsert eder.

        Bu yöntem JSON/Parquet'te aynı ``source_id`` + ``sector`` satırını
        günceller; eski satırın yanına ikinci bir kopya eklemez. Similarity
        yeniden hesaplanır, fakat detection confidence/FPP alanları yalnızca
        takip payload'ı açıkça taşıyorsa güncellenir.
        """

        if self._closed:
            raise RuntimeError("Kapatılmış OutputManager tekrar kullanılamaz.")
        if not isinstance(record, TransitCandidateRecord):
            raise TypeError("record TransitCandidateRecord olmalıdır.")

        validation = coerce_followup_result(
            followup_result,
            target_id=record.source_id,
        )
        if validation.mass_mearth is not None and not (
            record.planet_mass_mearth is not None and record.planet_mass_mearth > 0
        ):
            record.planet_mass_mearth = validation.mass_mearth
            record.mass_status = "measured"
        elif record.planet_mass_mearth is not None and record.planet_mass_mearth > 0:
            record.mass_status = "measured"

        similarity = score_earth_similarity(
            record.earth_similarity_profile or self.earth_similarity_profile,
            planet_radius_rearth=record.planet_radius_rearth,
            planet_mass_mearth=record.planet_mass_mearth,
            insolation_s_earth=record.insolation_s_earth,
            equilibrium_temperature_k=record.equilibrium_temperature_k,
            density_gcm3=record.planet_density_gcm3,
            semi_major_axis_au=record.semi_major_axis_au,
            stellar_teff_k=record.teff_k,
        )
        record.earth_similarity_profile = similarity.profile
        record.earth_similarity_definition_version = similarity.definition_version
        record.earth_similarity_score = similarity.score
        record.earth_similarity_p05 = similarity.score_p05
        record.earth_similarity_p50 = similarity.score_p50
        record.earth_similarity_p95 = similarity.score_p95
        record.earth_similarity_completeness = similarity.measurement_completeness
        record.earth_similarity_components = json.dumps(
            {key: component.to_dict() for key, component in similarity.components.items()},
            ensure_ascii=False,
            sort_keys=True,
        )
        record.earth_similarity_missing_dimensions = json.dumps(
            list(similarity.missing_dimensions), ensure_ascii=False
        )
        record.earth_similarity_missing_required = json.dumps(
            list(similarity.missing_required_dimensions), ensure_ascii=False
        )
        record.earth_similarity_notes = json.dumps(list(similarity.notes), ensure_ascii=False)
        record.earth_similarity_uncertainty_available = similarity.uncertainty_available

        if validation.confirmed and similarity.is_strict_candidate:
            record.earth_analog_class = "CONFIRMED_EARTH_TWIN"
            record.earth_twin_status = "confirmed_earth_twin"
        else:
            record.earth_analog_class = similarity.classification
            record.earth_twin_status = {
                "EARTH_TWIN_CANDIDATE": "earth_twin_candidate",
                "PHOTOMETRIC_EARTH_ANALOG": "photometric_earth_like_candidate",
            }.get(similarity.classification, similarity.classification.lower())

        record.followup_confirmed = validation.confirmed
        record.followup_status = validation.status
        record.followup_evidence_quality = validation.evidence_quality
        record.followup_sources = json.dumps(list(validation.sources), ensure_ascii=False)
        record.followup_observation_ids = json.dumps(
            list(validation.observation_ids), ensure_ascii=False
        )
        record.followup_evidence = json.dumps(validation.to_dict(), ensure_ascii=False)
        if validation.false_positive_probability is not None:
            record.false_positive_probability = validation.false_positive_probability
            record.fpp = validation.false_positive_probability
            # Follow-up FPP'i gözlem raporu üzerinden gelir; pipeline'ın
            # heuristik vetting proxy'sinden farklı bir kaynaktır.
            record.fpp_method = "followup_evidence_reported"

        self.json_writer.write_candidate(record)
        self.parquet_writer.upsert(record)
        if record not in self._records:
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
