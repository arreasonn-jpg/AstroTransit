"""Çıktı sistemi testleri."""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from astrotransit.data.catalog_client import StellarProperties
from astrotransit.outputs.schemas import TransitCandidateRecord, build_record
from astrotransit.validation.followup import FollowupEvidence
from astrotransit.outputs.parquet_writer import ParquetWriter
from astrotransit.outputs.json_writer import JSONWriter, NumpyEncoder
from astrotransit.outputs.csv_export import CSVExporter
from astrotransit.outputs.writers import OutputManager


class TestTransitCandidateRecord:
    """Standart kayıt testleri."""

    def test_default_creation(self):
        rec = TransitCandidateRecord()
        assert rec.source_id == ""
        assert rec.period == 0.0
        assert rec.candidate_class == ""
        assert rec.followup_confirmed is False
        assert rec.to_nested_dict()["followup"]["status"] == "not_confirmed"

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

    def test_fpp_method_in_flat_dict(self):
        rec = TransitCandidateRecord(source_id="TEST", fpp_method="heuristic_vetting_weighted_v1")
        flat = rec.to_flat_dict()
        assert flat["fpp_method"] == "heuristic_vetting_weighted_v1"
        nested = rec.to_nested_dict()
        assert nested["vetting"]["fpp_method"] == "heuristic_vetting_weighted_v1"

    def test_parquet_schema_treats_fpp_method_as_string(self, tmp_output_dir):
        import pyarrow as pa

        writer = ParquetWriter(tmp_output_dir / "parquet")
        field = writer.schema.field("fpp_method")
        assert field.type == pa.string()


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

    def test_append_preserves_existing_rows(self, tmp_output_dir):
        parquet_dir = tmp_output_dir / "parquet"
        first = TransitCandidateRecord(source_id="TIC 1", sector=1)
        second = TransitCandidateRecord(source_id="TIC 2", sector=2)

        with ParquetWriter(parquet_dir) as writer:
            writer.append(first)
        with ParquetWriter(parquet_dir) as writer:
            writer.append(second)

        loaded = ParquetWriter.read(parquet_dir / "astrotransit_candidates.parquet")
        assert set(loaded["source_id"]) == {"TIC 1", "TIC 2"}

    def test_empty_close_does_not_truncate_existing_rows(self, tmp_output_dir):
        parquet_dir = tmp_output_dir / "parquet"
        with ParquetWriter(parquet_dir) as writer:
            writer.append(TransitCandidateRecord(source_id="TIC 1", sector=1))

        with ParquetWriter(parquet_dir):
            pass

        loaded = ParquetWriter.read(parquet_dir / "astrotransit_candidates.parquet")
        assert len(loaded) == 1


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

    def test_followup_update_upserts_json_and_parquet(self, tmp_output_dir):
        manager = OutputManager(output_dir=tmp_output_dir / "followup_manager")
        candidate = {
            "target_id": "TIC 777",
            "sector": 14,
            "period": 365.25,
            "period_err": 0.1,
            "t0": 1.0,
            "rp_rs": 0.0092,
            "depth": 0.000085,
            "duration": 0.5,
            "confirmed": True,
            "transit_times": [],
        }
        record = build_record(
            candidate=candidate,
            stellar_props=StellarProperties(teff=5778.0, radius=1.0, mass=1.0),
            earth_similarity_profile="strict_earth_twin",
        )
        manager.append(record)
        manager.update_followup(
            record,
            FollowupEvidence(
                source="RV campaign",
                observation_type="radial_velocity",
                observation_ids=("rv-777",),
                confirmed=True,
                mass_mearth=1.0,
                false_positive_probability=0.01,
            ),
        )
        manager.close()

        loaded = ParquetWriter.read(manager.parquet_path)
        assert len(loaded) == 1
        assert bool(loaded.loc[0, "followup_confirmed"]) is True
        assert loaded.loc[0, "earth_twin_status"] == "confirmed_earth_twin"
        json_files = list((tmp_output_dir / "followup_manager" / "json").glob("*.json"))
        assert len(json_files) == 1
        payload = JSONWriter.read(json_files[0])
        assert payload["followup"]["confirmed"] is True
        assert payload["earth_similarity"]["status"] == "confirmed_earth_twin"

        reopened = OutputManager(output_dir=tmp_output_dir / "followup_manager")
        found = reopened.find_record("TIC 777", 14)
        assert found is not None
        assert found.followup_confirmed is True
        reopened.close()

    def test_output_manager_exports_csv_while_open(self, tmp_output_dir):
        manager = OutputManager(output_dir=tmp_output_dir / "manager")
        manager.append(TransitCandidateRecord(source_id="TIC 42", sector=3))

        path = manager.export_csv()
        loaded = pd.read_csv(path)
        manager.close()

        assert len(loaded) == 1
        assert loaded.loc[0, "source_id"] == "TIC 42"