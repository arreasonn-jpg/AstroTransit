#!/usr/bin/env python3
"""Screen deterministic real-TESS candidates for the injection host corpus."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from astrotransit.data.catalog_client import CatalogClient
from astrotransit.data.tess_client import TESSClient
from astrotransit.detection.cascade import CascadeDetector
from astrotransit.preprocessing.pipeline import TESSPreprocessingPipeline
from astrotransit.settings import get_settings


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tic_number(value: Any) -> str:
    return str(value).upper().replace("TIC", "").strip()


def _excluded_ids(path: Path) -> set[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("cases", []) if isinstance(payload, dict) else payload
    return {
        _tic_number(row.get("target_id", row.get("tic_id", "")))
        for row in rows
        if isinstance(row, dict)
    }


def _finite_positive(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and parsed > 0


def _candidate_rows(pool: Path, excluded: set[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with pool.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        required = {"tid", "source_id", "sector_count", "sector_list", "st_tmag", "st_teff", "st_rad"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError(f"Candidate pool missing columns: {sorted(required)}")
        for index, row in enumerate(reader):
            tic = _tic_number(row["tid"])
            sectors = [int(item) for item in str(row["sector_list"]).split(",") if item.strip()]
            reason = None
            if tic in excluded:
                reason = "labelled_toi_or_tfop_history"
            elif int(row["sector_count"]) < 2 or len(sectors) < 2:
                reason = "fewer_than_two_catalog_sectors"
            elif not all(_finite_positive(row[key]) for key in ("st_tmag", "st_teff", "st_rad")):
                reason = "nonfinite_pool_stellar_metadata"
            if reason is None:
                rows.append({
                    "pool_index": index,
                    "target_id": f"TIC {tic}",
                    "tic_id": tic,
                    "catalog_sectors": sectors,
                    "screen_sectors": [sectors[0], sectors[-1]],
                    "pool_tmag": float(row["st_tmag"]),
                    "pool_teff_k": float(row["st_teff"]),
                    "pool_radius_rsun": float(row["st_rad"]),
                })
    return rows


def _screen_one(row, tess, catalog, preprocessing):
    target_id = row["target_id"]
    audit = {"target_id": target_id, "pool_index": row["pool_index"], "screen_sectors": row["screen_sectors"], "accepted": False, "reason": ""}
    try:
        stellar = catalog.get_stellar_properties(target_id)
        if not (_finite_positive(stellar.radius) and _finite_positive(stellar.mass)):
            audit["reason"] = "missing_finite_catalog_radius_or_mass"
            audit["stellar_source"] = stellar.source
            return None, audit
        detector = CascadeDetector(settings=get_settings(), stellar_radius=float(stellar.radius), stellar_mass=float(stellar.mass))
        sector_rows = []
        for sector in row["screen_sectors"]:
            light_curve = tess.get_lightcurve(target_id, sector=sector)
            detrended = preprocessing.run(light_curve).detrended
            baseline = float(detrended.time[-1] - detrended.time[0])
            if baseline < 20.0:
                audit["reason"] = f"valid_baseline_below_20_days_sector_{sector}"
                return None, audit
            candidate = detector.detect(detrended)
            if candidate.has_candidate:
                audit["reason"] = f"pre_injection_candidate_{candidate.status.value}_sector_{sector}"
                audit["candidate_period_days"] = float(candidate.period)
                return None, audit
            flux = np.asarray(detrended.flux, dtype=float)
            median = float(np.nanmedian(flux))
            sector_rows.append({
                "sector": int(sector), "n_points": int(detrended.n_points), "baseline_days": baseline,
                "time_start_btjd": float(detrended.time[0]), "time_end_btjd": float(detrended.time[-1]),
                "noise_ppm": float(detrended.noise_ppm), "residual_rms": float(detrended.residual_rms),
                "variability_mad_ppm": float(1.4826 * np.nanmedian(np.abs(flux - median)) * 1e6),
                "pre_injection_candidate": False,
            })
        combined_baseline = max(item["time_end_btjd"] for item in sector_rows) - min(item["time_start_btjd"] for item in sector_rows)
        accepted = {
            "target_id": target_id, "tic_id": row["tic_id"], "pool_index": row["pool_index"],
            "sectors": row["screen_sectors"], "combined_baseline_days": combined_baseline,
            "median_noise_ppm": float(np.median([item["noise_ppm"] for item in sector_rows])),
            "median_variability_mad_ppm": float(np.median([item["variability_mad_ppm"] for item in sector_rows])),
            "stellar": {"radius_rsun": float(stellar.radius), "mass_msun": float(stellar.mass), "teff_k": float(stellar.teff), "tmag": float(stellar.tmag), "source": stellar.source},
            "sector_measurements": sector_rows,
            "selection_evidence": {"no_labelled_toi_or_tfop_history_at_snapshot": True, "no_pre_injection_pipeline_candidate": True, "real_tess_spoc_120s": True},
        }
        audit["accepted"] = True
        audit["reason"] = "accepted"
        return accepted, audit
    except Exception as exc:
        audit["reason"] = f"screen_error:{type(exc).__name__}:{exc}"
        return None, audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pool", type=Path, required=True)
    parser.add_argument("--labelled-corpus", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--candidate-limit", type=int, default=30)
    parser.add_argument("--required-hosts", type=int, default=10)
    args = parser.parse_args()
    if args.candidate_limit < args.required_hosts:
        raise SystemExit("candidate-limit must be >= required-hosts")
    excluded = _excluded_ids(args.labelled_corpus)
    candidates = _candidate_rows(args.pool, excluded)[:args.candidate_limit]
    settings = get_settings()
    tess = TESSClient(author=settings.tess.author, exptime=settings.tess.exptime, quality_bitmask=settings.tess.quality_bitmask, cache_dir=settings.general.temp_dir + "/quiet-host-prescreen", cache_ttl_hours=settings.tess.cache_ttl_hours, use_cache=True)
    catalog = CatalogClient()
    preprocessing = TESSPreprocessingPipeline(settings=settings)
    selected, audit_rows = [], []
    for row in candidates:
        host, audit = _screen_one(row, tess, catalog, preprocessing)
        audit_rows.append(audit)
        if host is not None:
            selected.append(host)
        if len(selected) == args.required_hosts:
            break
    args.output_dir.mkdir(parents=True, exist_ok=True)
    status = "frozen" if len(selected) == args.required_hosts else "insufficient_quiet_hosts"
    payload = {
        "schema_version": "1.0", "corpus": "real_noise_injection_quiet_hosts_v1", "status": status,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "selection_policy": "pool_order_after_label_exclusion_then_two_sector_production_prescreen_v1",
        "required_host_count": args.required_hosts, "selected_host_count": len(selected), "candidate_limit": args.candidate_limit,
        "source_pool": str(args.pool), "source_pool_sha256": _sha256(args.pool),
        "labelled_corpus": str(args.labelled_corpus), "labelled_corpus_sha256": _sha256(args.labelled_corpus),
        "hosts": selected,
        "claim_boundary": "Selected real-noise injection hosts are not a population-representative quiet-star sample.",
    }
    quiet_path = args.output_dir / "quiet_hosts.json"
    audit_path = args.output_dir / "prescreen_audit.json"
    quiet_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit_path.write_text(json.dumps({"screened": audit_rows}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if status != "frozen":
        print(f"Only {len(selected)}/{args.required_hosts} quiet hosts selected")
        return 2
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    contract["status"] = "pending_run"
    contract["status_reason"] = "quiet_host_corpus_frozen_injection_trials_not_run"
    contract["host_corpus"]["status"] = "frozen"
    contract["host_corpus"]["sha256"] = _sha256(quiet_path)
    args.contract.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Frozen {len(selected)} quiet hosts at {quiet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
