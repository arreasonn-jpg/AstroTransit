"""AstroTransit çıktı ve kalıcı kayıt katmanı.

Pipeline sonuçlarını tek bir şemada tutar ve JSON, Parquet ve CSV
formatlarına aktarır.  Yazıcılar mümkün olduğunca idempotent ve
kapatıldıktan sonra güvenli şekilde tekrar çağrılabilir olacak şekilde
tasarlanmıştır.
"""

from astrotransit.outputs.csv_export import CSVExporter
from astrotransit.outputs.json_writer import JSONWriter, NumpyEncoder
from astrotransit.outputs.l1_pool import (
    L1_POOL_SCHEMA_VERSION,
    L1PoolRecord,
    build_l1_pool_payload,
    build_l1_pool_record,
    write_l1_pool_json,
)
from astrotransit.outputs.migration import (
    flatten_nested_record,
    migrate_json,
    migrate_parquet,
    upgrade_flat_record,
)
from astrotransit.outputs.parquet_writer import ParquetWriter
from astrotransit.outputs.schemas import (
    TransitCandidateRecord,
    build_long_period_record,
    build_record,
)
from astrotransit.outputs.writers import OutputManager

__all__ = [
    "CSVExporter",
    "JSONWriter",
    "L1_POOL_SCHEMA_VERSION",
    "L1PoolRecord",
    "NumpyEncoder",
    "OutputManager",
    "ParquetWriter",
    "TransitCandidateRecord",
    "build_l1_pool_payload",
    "build_l1_pool_record",
    "build_long_period_record",
    "build_record",
    "flatten_nested_record",
    "migrate_json",
    "migrate_parquet",
    "upgrade_flat_record",
    "write_l1_pool_json",
]
