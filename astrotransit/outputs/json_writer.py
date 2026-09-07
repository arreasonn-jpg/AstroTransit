"""JSON çıktı yazıcısı."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
from loguru import logger

from astrotransit.outputs.schemas import TransitCandidateRecord


class NumpyEncoder(json.JSONEncoder):
    """NumPy, Path, Enum ve dataclass değerlerini JSON'a dönüştürür.

    IEEE ``NaN``/``inf`` değerleri bilimsel çıktıda geçerli ölçüm değildir;
    JSON standardına uygun olarak ``null`` yazılır.
    """

    def default(self, obj: Any) -> Any:  # noqa: D401
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, Path):
            return str(obj)
        if isinstance(obj, Enum):
            return obj.value
        if is_dataclass(obj):
            return asdict(obj)
        return super().default(obj)

    def encode(self, obj: Any) -> str:
        return super().encode(_sanitize(obj))


def _sanitize(value: Any) -> Any:
    """JSON ağacını non-finite sayılardan arındırır."""

    if isinstance(value, dict):
        return {str(k): _sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v) for v in value]
    if isinstance(value, np.ndarray):
        return _sanitize(value.tolist())
    if isinstance(value, np.generic):
        return _sanitize(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return _sanitize(value.value)
    if is_dataclass(value):
        return _sanitize(asdict(value))
    return value


class JSONWriter:
    """Transit aday kayıtlarını JSON dosyalarına yazar."""

    def __init__(self, output_dir: str | Path, indent: int = 2):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.indent = indent

    @staticmethod
    def _safe_stem(record: TransitCandidateRecord) -> str:
        source = str(record.source_id or "target")
        source = source.replace(" ", "_").replace("/", "_").replace("\\", "_")
        return f"{source}_S{int(record.sector):02d}"

    def write_candidate(
        self,
        record: TransitCandidateRecord,
        path: str | Path | None = None,
    ) -> Path:
        """Bir kaydı JSON'a yazar ve dosya yolunu döndürür."""

        if path is None:
            path = self.output_dir / f"{self._safe_stem(record)}.json"
        else:
            path = Path(path)
            if not path.is_absolute():
                path = self.output_dir / path

        path.parent.mkdir(parents=True, exist_ok=True)
        payload = record.to_nested_dict()
        # JSON içindeki files.json_path alanı dosyanın gerçek yolunu göstersin.
        payload.setdefault("files", {})["json_path"] = str(path)

        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(
                payload,
                handle,
                cls=NumpyEncoder,
                ensure_ascii=False,
                indent=self.indent,
                allow_nan=False,
            )
            handle.write("\n")
        temp_path.replace(path)
        logger.debug(f"JSON aday kaydı yazıldı: {path}")
        return path

    def write_many(
        self,
        records: Iterable[TransitCandidateRecord],
        *,
        filenames: Optional[Iterable[str | Path]] = None,
    ) -> list[Path]:
        paths: list[Path] = []
        names = iter(filenames) if filenames is not None else None
        for record in records:
            paths.append(self.write_candidate(record, next(names) if names is not None else None))
        return paths

    @staticmethod
    def read(path: str | Path) -> dict[str, Any]:
        """JSON aday kaydını okur."""

        with Path(path).open("r", encoding="utf-8") as handle:
            return json.load(handle)
