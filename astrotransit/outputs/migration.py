"""Eski JSON/Parquet çıktılarını güncel şemaya taşıma yardımcıları."""

from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path
from typing import Any, Mapping

from astrotransit.outputs.json_writer import JSONWriter
from astrotransit.outputs.parquet_writer import ParquetWriter
from astrotransit.outputs.schemas import SCHEMA_VERSION, TransitCandidateRecord


def upgrade_flat_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """Flat eski satırı mevcut dataclass alanlarıyla tamamlar."""

    defaults = TransitCandidateRecord().to_flat_dict()
    known = {item.name for item in fields(TransitCandidateRecord)}
    upgraded = {key: value for key, value in row.items() if key in known}
    defaults.update(upgraded)
    defaults["schema_version"] = SCHEMA_VERSION
    defaults.setdefault("earth_similarity_definition_version", "1.0")
    defaults.setdefault("followup_status", "not_confirmed")
    defaults.setdefault("followup_evidence_quality", "none")
    defaults.setdefault("followup_sources", "[]")
    defaults.setdefault("followup_observation_ids", "[]")
    defaults.setdefault("followup_evidence", "{}")
    for field_name in (
        "earth_similarity_missing_dimensions",
        "earth_similarity_missing_required",
        "earth_similarity_notes",
        "source_sectors",
        "followup_sources",
        "followup_observation_ids",
        "flags",
        "anomaly_flags",
    ):
        defaults[field_name] = _json_text(defaults.get(field_name), default=[])
    for field_name in ("earth_similarity_components", "followup_evidence"):
        defaults[field_name] = _json_text(defaults.get(field_name), default={})
    return defaults


def _json_text(value: Any, *, default: Any) -> str:
    if value is None or value == "":
        return json.dumps(default, ensure_ascii=False)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = [value] if isinstance(default, list) else {"value": value}
    else:
        parsed = value
    if isinstance(default, list):
        if not isinstance(parsed, list):
            parsed = [parsed]
    elif not isinstance(parsed, dict):
        parsed = {"value": parsed}
    return json.dumps(parsed, ensure_ascii=False, default=str)


def flatten_nested_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Eski bölümlenmiş JSON payload'ını flat kayıt satırına çevirir."""

    if "metadata" not in payload and "target" not in payload:
        return upgrade_flat_record(payload)

    result: dict[str, Any] = {}
    sections = {key: payload.get(key, {}) or {} for key in (
        "metadata", "target", "stellar", "detection", "parameters", "derived",
        "earth_similarity", "search", "followup", "quality", "vetting", "score",
        "modeling", "files",
    )}
    target = sections["target"]
    stellar = sections["stellar"]
    result.update({
        "source_id": target.get("source_id", ""),
        "tic_id": target.get("tic_id", 0),
        "mission": target.get("mission", "TESS"),
        "sector": target.get("sector", -1),
        "instrument": target.get("instrument", "TESS"),
        "radius_rsun": stellar.get("radius_rsun", 0.0),
        "mass_msun": stellar.get("mass_msun", 0.0),
        "teff_k": stellar.get("teff_k", 0.0),
        "tmag": stellar.get("tmag", 0.0),
        "logg": stellar.get("logg", 0.0),
        "ra_deg": stellar.get("ra_deg", 0.0),
        "dec_deg": stellar.get("dec_deg", 0.0),
    })
    detection = sections["detection"]
    for key, source in (("bls", "bls"), ("tls", "tls"), ("cascade", "cascade")):
        block = detection.get(key, {}) or {}
        if key == "bls":
            result.update({"bls_period": block.get("period_days", 0.0), "bls_power": block.get("power", 0.0), "bls_depth_ppm": block.get("depth_ppm", 0.0)})
        elif key == "tls":
            result.update({"tls_period": block.get("period_days", 0.0), "tls_sde": block.get("sde", 0.0), "tls_snr": block.get("snr", 0.0), "tls_odd_even_mismatch": block.get("odd_even_mismatch", 0.0)})
        else:
            result.update({"cascade_status": block.get("status", ""), "cascade_confirmed": block.get("confirmed", False)})
    parameters = sections["parameters"]
    result.update({
        "period": parameters.get("period_days", 0.0),
        "period_err": parameters.get("period_err_days", 0.0),
        "t0": parameters.get("t0_btjd", 0.0),
        "duration_hours": parameters.get("duration_hours", 0.0),
        "depth": parameters.get("depth", 0.0),
        "depth_ppm": parameters.get("depth_ppm", 0.0),
        "rp_rs": parameters.get("rp_rs", 0.0),
        "rp_rs_err": parameters.get("rp_rs_err", 0.0),
        "impact_parameter": parameters.get("impact_parameter", 0.0),
        "a_over_rs": parameters.get("a_over_rs", 0.0),
        "inclination_deg": parameters.get("inclination_deg", 0.0),
        "u1": parameters.get("u1", 0.0), "u2": parameters.get("u2", 0.0),
        "log_jitter": parameters.get("log_jitter", 0.0), "baseline": parameters.get("baseline", 1.0),
    })
    derived = sections["derived"]
    result.update({
        "planet_radius_rearth": derived.get("planet_radius_rearth", 0.0),
        "planet_radius_rjup": derived.get("planet_radius_rjup", 0.0),
        "semi_major_axis_au": derived.get("semi_major_axis_au", 0.0),
        "equilibrium_temperature_k": derived.get("equilibrium_temperature_k", 0.0),
        "equilibrium_temperature_albedo": derived.get("equilibrium_temperature_albedo", 0.3),
        "insolation_flux": derived.get("insolation_flux", 0.0),
        "insolation_s_earth": derived.get("insolation_s_earth", 0.0),
        "stellar_density_gcm3": derived.get("stellar_density_gcm3", 0.0),
        "planet_mass_mearth": derived.get("planet_mass_mearth"),
        "planet_density_gcm3": derived.get("planet_density_gcm3"),
        "transit_depth_ppm": derived.get("transit_depth_ppm", 0.0),
        "coverage_baseline_days": derived.get("coverage_baseline_days", 0.0),
        "observed_days": derived.get("observed_days", 0.0),
        "n_observed_transits": derived.get("n_observed_transits", 0),
    })
    similarity = sections["earth_similarity"]
    result.update({
        "earth_similarity_profile": similarity.get("profile", ""),
        "earth_similarity_definition_version": similarity.get("definition_version", "1.0"),
        "earth_similarity_score": similarity.get("score", similarity.get("score_p50", 0.0)),
        "earth_similarity_p05": similarity.get("score_p05", 0.0),
        "earth_similarity_p50": similarity.get("score_p50", similarity.get("score", 0.0)),
        "earth_similarity_p95": similarity.get("score_p95", 0.0),
        "earth_similarity_completeness": similarity.get("measurement_completeness", 0.0),
        "earth_analog_class": similarity.get("classification", ""),
        "earth_twin_status": similarity.get("status", "unverified"),
        "earth_similarity_components": _json_text(similarity.get("components", {}), default={}),
        "earth_similarity_missing_dimensions": _json_text(similarity.get("missing_dimensions", []), default=[]),
        "earth_similarity_missing_required": _json_text(similarity.get("missing_required_dimensions", []), default=[]),
        "earth_similarity_notes": _json_text(similarity.get("notes", []), default=[]),
        "earth_similarity_uncertainty_available": similarity.get("uncertainty_available", False),
        "mass_status": similarity.get("mass_status", "unavailable"),
    })
    search = sections["search"]
    result.update({
        "search_channel": search.get("channel", "sector_cascade"),
        "source_sectors": _json_text(search.get("source_sectors", []), default=[]),
        "long_period_identifiability": search.get("long_period_identifiability", ""),
        "long_period_screening": search.get("long_period_screening", False),
    })
    followup = sections["followup"]
    result.update({
        "followup_confirmed": followup.get("confirmed", False),
        "followup_status": followup.get("status", "not_confirmed"),
        "followup_evidence_quality": followup.get("evidence_quality", "none"),
        "followup_sources": _json_text(followup.get("sources", []), default=[]),
        "followup_observation_ids": _json_text(followup.get("observation_ids", []), default=[]),
        "followup_evidence": _json_text(followup.get("evidence", {}), default={}),
    })
    quality = sections["quality"]
    result.update({key: quality.get(key, 0.0) for key in (
        "snr_adopted", "snr_tls", "snr_dutycycle", "noise_ppm", "cdpp_1hr_ppm",
        "data_completeness", "n_points", "n_transits", "residual_rms_ppm",
        "transit_symmetry", "timing_rms_min",
    )})
    vetting = sections["vetting"]
    result.update({
        "fpp": vetting.get("fpp", vetting.get("false_positive_probability")),
        "false_positive_probability": vetting.get("false_positive_probability", vetting.get("fpp")),
        "detection_confidence": payload.get("detection_confidence", vetting.get("detection_confidence", "UNKNOWN")),
        "is_false_positive": vetting.get("is_false_positive", False),
        "is_variable_star": vetting.get("is_variable_star", False),
        "is_binary_suspect": vetting.get("is_binary_suspect", False),
        "secondary_eclipse_depth_ppm": vetting.get("secondary_eclipse_depth_ppm", 0.0),
        "n_pass": vetting.get("n_pass", 0), "n_fail": vetting.get("n_fail", 0), "n_warn": vetting.get("n_warn", 0),
        "flags": _json_text(vetting.get("flags", []), default=[]),
    })
    score = sections["score"]
    result.update({
        "total_score": score.get("total_score", 0.0),
        "candidate_class": score.get("candidate_class", ""),
        "is_anomalous": score.get("is_anomalous", False),
        "anomaly_flags": _json_text(score.get("anomaly_flags", []), default=[]),
    })
    result.update(sections["modeling"])
    result.update({
        "json_path": sections["files"].get("json_path", ""),
        "figure_dir": sections["files"].get("figure_dir", ""),
        "created_at": sections["metadata"].get("created_at", ""),
        "schema_version": sections["metadata"].get("schema_version", "1.0"),
    })
    return upgrade_flat_record(result)


def migrate_json(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(input_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    record = TransitCandidateRecord(**flatten_nested_record(payload))
    destination = Path(output_path) if output_path is not None else source
    destination.parent.mkdir(parents=True, exist_ok=True)
    JSONWriter(destination.parent).write_candidate(record, destination.name)
    return destination


def migrate_parquet(input_path: str | Path, output_path: str | Path | None = None) -> Path:
    source = Path(input_path)
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover
        raise ImportError("Parquet migration için pyarrow gereklidir.") from exc
    rows = [upgrade_flat_record(row) for row in pq.read_table(source).to_pylist()]
    destination = Path(output_path) if output_path is not None else source
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(rows, schema=ParquetWriter._arrow_schema()),
        temporary,
        compression="zstd",
    )
    temporary.replace(destination)
    return destination


__all__ = [
    "flatten_nested_record",
    "migrate_json",
    "migrate_parquet",
    "upgrade_flat_record",
]
