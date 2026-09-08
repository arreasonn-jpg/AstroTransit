"""Parquet çıktı yazıcısı.

PyArrow yalnızca Parquet gerçekten kullanıldığında yüklenir; böylece JSON/CSV
kullanıcıları eksik opsiyonel bağımlılık nedeniyle import hatası almaz.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from loguru import logger

from astrotransit.outputs.schemas import TransitCandidateRecord


class ParquetWriter:
    """Transit kayıtlarını batch halinde Parquet row-group'larına yazar."""

    def __init__(
        self,
        output_dir: str | Path,
        filename: str = "astrotransit_candidates.parquet",
        batch_size: int = 100,
        compression: str = "zstd",
    ):
        if batch_size < 1:
            raise ValueError("batch_size en az 1 olmalıdır.")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.output_dir / filename
        self.batch_size = int(batch_size)
        self.compression = compression
        self._buffer: list[dict[str, Any]] = []
        self._existing_rows: list[dict[str, Any]] = []
        self._writer = None
        self._schema = None
        self._closed = False
        self.n_written = 0

        # A new writer must not silently truncate a catalog produced by an
        # earlier process.  Existing rows are loaded lazily into the first
        # batch; the public count still reports only rows appended by this
        # instance.
        if self.path.exists():
            try:
                import pyarrow.parquet as pq
                self._existing_rows = pq.read_table(self.path).to_pylist()
            except ImportError as exc:  # pragma: no cover - optional dependency
                raise ImportError("Var olan Parquet'i genişletmek için 'pyarrow' gereklidir.") from exc
            except Exception as exc:
                raise ValueError(f"Var olan Parquet dosyası okunamadı: {self.path}") from exc

    @staticmethod
    def _arrow_schema():
        try:
            import pyarrow as pa
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError("Parquet çıktısı için 'pyarrow' gereklidir.") from exc

        # Düz kayıt sözlüğündeki alanlar sabittir; nullable alanlar için
        # PyArrow field'ları nullable bırakılır.
        string_fields = {
            "source_id", "mission", "instrument", "cascade_status", "flags",
            "candidate_class", "anomaly_flags", "fit_method", "fit_status",
            "period_err_source", "rp_rs_err_source", "u1_err_source", "u2_err_source",
            "json_path", "figure_dir", "created_at", "schema_version",
            "earth_similarity_profile", "earth_similarity_definition_version",
            "earth_analog_class", "earth_twin_status",
            "earth_similarity_components", "earth_similarity_missing_dimensions",
            "earth_similarity_missing_required", "earth_similarity_notes", "mass_status",
            "search_channel", "source_sectors", "long_period_identifiability", "detection_confidence",
            "fpp_method", "claim_status", "failure_codes", "mcmc_quality",
            "followup_status", "followup_evidence_quality", "followup_sources",
            "followup_observation_ids", "followup_evidence",
        }
        bool_fields = {
            "cascade_confirmed", "is_false_positive", "is_variable_star",
            "is_binary_suspect", "is_anomalous", "posterior_available",
            "posterior_converged", "fallback_used", "mcmc_converged",
            "period_sampled", "rp_rs_sampled", "u1_sampled", "u2_sampled",
            "derived_errors_available", "earth_similarity_uncertainty_available",
            "long_period_screening", "followup_confirmed",
        }
        int_fields = {
            "tic_id", "sector", "n_points", "n_transits", "n_observed_transits",
            "n_pass", "n_fail", "n_warn", "n_divergences",
        }

        fields = []
        for name in TransitCandidateRecord.__dataclass_fields__:
            if name in string_fields:
                dtype = pa.string()
            elif name in bool_fields:
                dtype = pa.bool_()
            elif name in int_fields:
                dtype = pa.int64()
            else:
                dtype = pa.float64()
            fields.append(pa.field(name, dtype, nullable=True))
        return pa.schema(fields)

    @property
    def schema(self):
        if self._schema is None:
            self._schema = self._arrow_schema()
        return self._schema

    def append(self, record: TransitCandidateRecord | dict[str, Any]) -> None:
        """Kaydı buffer'a ekler; batch dolunca diske yazar."""

        if self._closed:
            raise RuntimeError("Kapatılmış ParquetWriter'a kayıt eklenemez.")
        if isinstance(record, TransitCandidateRecord):
            row = record.to_flat_dict()
        elif isinstance(record, dict):
            row = dict(record)
        else:
            raise TypeError("record TransitCandidateRecord veya dict olmalıdır.")

        # Eksik kolonları null ile tamamla, bilinmeyen alanları sessizce
        # atma: şema dışı alanlar JSON'da kalabilir ama Parquet sözleşmesine
        # girmemelidir.
        row = {name: row.get(name) for name in self.schema.names}
        self._buffer.append(row)
        self.n_written += 1
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def append_many(self, records: Iterable[TransitCandidateRecord | dict[str, Any]]) -> None:
        for record in records:
            self.append(record)

    def flush(self) -> None:
        """Bekleyen kayıtları bir row group olarak yazar."""

        if self._writer is None and self._existing_rows:
            self._buffer = self._existing_rows + self._buffer
            self._existing_rows = []
        if not self._buffer:
            return
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError("Parquet çıktısı için 'pyarrow' gereklidir.") from exc

        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(
                self.path,
                self.schema,
                compression=self.compression,
                use_dictionary=True,
            )

        table = pa.Table.from_pylist(self._buffer, schema=self.schema)
        self._writer.write_table(table)
        self._buffer.clear()
        logger.debug(f"Parquet batch yazıldı: {self.path}")

    def upsert(
        self,
        record: TransitCandidateRecord | dict[str, Any],
        *,
        identity_fields: tuple[str, ...] = ("source_id", "sector"),
    ) -> None:
        """Aynı kimlikteki satırı değiştirir; yoksa yeni satır ekler.

        Parquet row-group'ları yerinde düzenlenemediği için mevcut writer
        güvenli biçimde kapatılır, tablo geçici dosyaya yeniden yazılır ve
        writer yeni append'ler için tekrar açılabilir hale getirilir.
        """

        if self._closed:
            raise RuntimeError("Kapatılmış ParquetWriter güncellenemez.")
        if isinstance(record, TransitCandidateRecord):
            replacement = record.to_flat_dict()
        elif isinstance(record, dict):
            replacement = dict(record)
        else:
            raise TypeError("record TransitCandidateRecord veya dict olmalıdır.")
        if not identity_fields:
            raise ValueError("identity_fields boş olamaz.")

        self.close()
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise ImportError("Parquet güncellemesi için 'pyarrow' gereklidir.") from exc

        rows: list[dict[str, Any]] = []
        if self.path.exists():
            rows = pq.read_table(self.path).to_pylist()
        replacement = {name: replacement.get(name) for name in self.schema.names}
        replaced = False
        for index, row in enumerate(rows):
            if all(row.get(name) == replacement.get(name) for name in identity_fields):
                rows[index] = replacement
                replaced = True
                break
        if not replaced:
            rows.append(replacement)

        temporary_path = self.path.with_suffix(self.path.suffix + ".tmp")
        table = pa.Table.from_pylist(rows, schema=self.schema)
        pq.write_table(table, temporary_path, compression=self.compression)
        temporary_path.replace(self.path)

        # Keep the logical writer open for later pipeline outputs.
        self._buffer = []
        self._existing_rows = rows
        self._writer = None
        self._closed = False
        self.n_written = 0

    def close(self) -> None:
        """Kalan kayıtları yazar ve Parquet dosyasını kapatır."""

        if self._closed:
            return
        self.flush()
        if self._writer is not None:
            self._writer.close()
        elif self.n_written == 0 and not self._existing_rows:
            # Boş yazıcıda bile geçerli bir dosya üretmek daha öngörülebilir.
            try:
                import pyarrow as pa
                import pyarrow.parquet as pq
                pq.write_table(
                    pa.Table.from_pylist([], schema=self.schema),
                    self.path,
                    compression=self.compression,
                )
            except ImportError as exc:  # pragma: no cover
                raise ImportError("Parquet çıktısı için 'pyarrow' gereklidir.") from exc
        self._closed = True
        logger.info(f"Parquet yazımı tamamlandı: {self.path} ({self.n_written} kayıt)")

    def __enter__(self) -> "ParquetWriter":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    @staticmethod
    def read(path: str | Path):
        """Parquet dosyasını pandas DataFrame olarak okur."""

        try:
            import pandas as pd
        except ImportError as exc:  # pragma: no cover
            raise ImportError("Parquet okumak için 'pandas' gereklidir.") from exc
        return pd.read_parquet(Path(path))
