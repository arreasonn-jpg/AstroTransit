"""Çıktı sistemi testleri."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astrotransit.outputs.schemas import TransitCandidateRecord
from astrotransit.outputs.parquet_writer import ParquetWriter
from astrotransit.outputs.json_writer import JSONWriter, NumpyEncoder
from astrotransit.outputs.csv_export import CSVExporter


class TestTransitCandidateRecord:
    """Standart kayıt testleri."""

    def test_default_creation(self):
        rec = TransitCandidateRecord()
        assert rec.source_id == ""
        assert rec.period == 0.0
        assert rec.candidate_class == ""

    def test_to_dict(self):
        rec = TransitCandidateRecord(
            source_id="TIC 123",
            period=3.5,
            candidate_class="A",
        )
        d = rec.to_dict()
        assert d["source_id"] == "TIC 123"
        assert d["period"] == 3.5

    def test_to_flat_dict(self):
        rec = TransitCandidateRecord(source_id="TEST")
        flat = rec.to_flat_dict()
        assert isinstance(flat, dict)


class TestParquetWriter:
    """Parquet yazıcı testleri."""

    def test_write_and_read(self, tmp_output_dir):
        parquet_dir = tmp_output_dir / "parquet"

        with ParquetWriter(parquet_dir, filename="test.parquet") as writer:
            for i in range(5):
                rec = TransitCandidateRecord(
                    source_id=f"TIC {i}",
                    sector=14,
                    period=float(i + 1),
                    candidate_class="B",
                )
                writer.append(rec)

        assert writer.n_written == 5

        df = ParquetWriter.read(parquet_dir / "test.parquet")
        assert len(df) == 5
        assert "source_id" in df.columns

    def test_batch_flush(self, tmp_output_dir):
        parquet_dir = tmp_output_dir / "parquet"

        writer = ParquetWriter(parquet_dir, batch_size=3)

        for i in range(7):
            rec = TransitCandidateRecord(source_id=f"TIC {i}", sector=1)
            writer.append(rec)

        writer.close()
        assert writer.n_written == 7


class TestJSONWriter:
    """JSON yazıcı testleri."""

    def test_write_candidate(self, tmp_output_dir):
        json_dir = tmp_output_dir / "json"
        writer = JSONWriter(json_dir)

        rec = TransitCandidateRecord(
            source_id="TIC 123456789",
            sector=14,
            period=3.5,
            depth_ppm=1000.0,
        )

        path = writer.write_candidate(rec)
        assert path.exists()

        data = JSONWriter.read(path)
        assert data["target"]["source_id"] == "TIC 123456789"
        assert data["parameters"]["period_days"] == 3.5

    def test_numpy_encoder(self):
        data = {
            "int": np.int64(42),
            "float": np.float64(3.14),
            "array": np.array([1, 2, 3]),
            "nan": np.float64(np.nan),
            "bool": np.bool_(True),
        }

        result = json.dumps(data, cls=NumpyEncoder)
        parsed = json.loads(result)

        assert parsed["int"] == 42
        assert abs(parsed["float"] - 3.14) < 1e-10
        assert parsed["array"] == [1, 2, 3]
        assert parsed["nan"] is None
        assert parsed["bool"] is True


class TestCSVExporter:
    """CSV dışa aktarma testleri."""

    def test_export_summary(self, tmp_output_dir):
        csv_dir = tmp_output_dir / "csv"
        exporter = CSVExporter(csv_dir)

        df = pd.DataFrame({
            "source_id": ["TIC 1", "TIC 2"],
            "sector": [14, 15],
            "period": [3.5, 7.2],
            "candidate_class": ["A", "B"],
            "total_score": [85.0, 65.0],
        })

        path = exporter.export_summary(df)
        assert path.exists()

        loaded = pd.read_csv(path)
        assert len(loaded) == 2