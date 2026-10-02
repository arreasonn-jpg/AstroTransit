"""Dondurulmuş blind domain holdout korpusu ve değerlendirme sözleşmesi.

Kapının iddiası basit: **hiçbir önceki kapıdan geçmemiş, harici etiketlere
sahip gerçek hedefler** üzerinde ölçüm yapmak. Bu modül yalnızca seçim
sözleşmesini (kimlik, kotalar, disjointness kanıtı) ve rapor şemasını tanımlar;
ışık eğrisi indirme/tespit adımı `scripts/validation/run_blind_holdout.py`
içindedir. Critik noktalar:

- Üyelik listesi **dedektör çıktılarına bakılarak seçilmez** (kendi kendini
  seçme ile şişirilmiş oran riski). Yegane seçim sinyali: sha256 seeded rank.
- Evren, `splits.assign_split(split_seed)` ile **blind_test** bölmesidir;
  development/validation bölmesindeki hedefler yapısal olarak dışlanır.
- Önceki kapılarda kullanılmış kimlikler (FP-run subseti, quiet-sky hostları,
  FPP kalibrasyon koortu, eski satır dosyaları) tamamen çıkarılır.
- Etiketler TFoP WG disposition korpusundan gelir; repo etiket uydurmaz.
- Oranlar değerlendirilemeyen satırların üzerinden hesaplanmaz; hata sayılır
  ve kapı kapalı kalır.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from astrotransit.validation.splits import assign_split

CAMPAIGN = "blind_domain_holdout_v1"
GATE_ID = "blind_domain_holdout"
LABELLED_CORPUS = "benchmarks/corpora/tfop_disposition_corpus_v1.json"
FP_RUN_SUBSET = "benchmarks/corpora/fp_run_subset_v1.json"
PRIOR_INJECTION_HOSTS = "validation_runs/v1_injection_recovery/real_noise_v1/input/quiet_hosts.json"
HOLDOUT_MANIFEST = "validation_runs/final_acceptance_v1/blind_holdout/holdout_manifest.json"
REQUIRED_OUTPUT = "validation_runs/final_acceptance_v1/blind_holdout/report.json"

#: Blind bölme ataması için donmuş tohum (korpusun bir parçası).
SPLIT_SEED = 13
#: Kota seçimi için donmuş tohum.
HOLDOUT_SEED = 20260918
PER_LABEL = 72
SELECTION_METHOD = "sha256_seeded_rank_within_label_and_disposition_stratum_v1"

#: Kabul eşikleri ölçümden ÖNCE ilan edilir (program.json ile aynı sayılar).
DECLARED_FLOOR_RECALL = 0.5
DECLARED_CEILING_FALSE_POSITIVE_RATE = 0.6
MINIMUM_CASES_PER_STRATUM = 8
MINIMUM_EVALUATED_CASES = 120

DISPOSITION_RE = re.compile(r"disposition '([A-Z*]+)'")
LABEL_GROUPS = {"planet": ("CP", "KP"), "false_positive": ("FP", "APC", "FA")}


def normalize_target_id(value: Any) -> str:
    return str(value).strip().split(".")[0]


def selection_rank(seed: int, target_id: str) -> str:
    """Etiketten/skordan bağımsız, tekrar üretilebilir sıralama anahtarı."""

    return hashlib.sha256(f"{seed}:{target_id}".encode()).hexdigest()


def disposition_code(reference: str) -> str:
    match = DISPOSITION_RE.search(reference or "")
    return match.group(1) if match else "UNCODED"


def stratum_key(label: str, reference: str) -> str:
    return f"{label}:{disposition_code(reference)}"


def allocate_quotas(pool: Mapping[str, int], total: int, *, minimum: int = 0) -> dict[str, int]:
    """Katman başına taban + havuz büyüklüğüyle orantılı tam sayı kotaları.

    ``minimum`` her katmanın **ölçülmesini** garanti eder (küçük havuzlarda
    oransal kota sıfıra düşüp katmanın hiç test edilmemesi engellenir); kalan
    kota havuz boyutlarıyla orantılı dağıtılır.
    """

    available = {key: int(value) for key, value in pool.items() if value > 0}
    if not available or total <= 0:
        return {key: 0 for key in pool}
    base = {key: min(available[key], max(0, int(minimum))) for key in available}
    quotas = dict(base)
    if sum(quotas.values()) > total:  # tabanlar toplamı aşarsa en büyük havuzdan kırp
        for key in sorted(available, key=lambda item: (-available[item], item)):
            if sum(quotas.values()) <= total:
                break
            quotas[key] = max(0, quotas[key] - 1)
        return {key: quotas.get(key, 0) for key in pool}

    remaining = total - sum(quotas.values())
    headroom = {key: available[key] - quotas[key] for key in available}
    headroom_total = sum(headroom.values())
    if remaining > 0 and headroom_total > 0:
        exact = {key: remaining * headroom[key] / headroom_total for key in available}
        for key, value in exact.items():
            quotas[key] += int(math.floor(value))
        leftover = remaining - sum(quotas[key] - base[key] for key in available)
        order = sorted(available, key=lambda key: (-(exact[key] - math.floor(exact[key])), key))
        for key in order:
            if leftover <= 0:
                break
            if quotas[key] < available[key]:
                quotas[key] += 1
                leftover -= 1
    return {key: quotas.get(key, 0) for key in pool}


def _ids_from(payload: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"target_id", "tic_id"} and not isinstance(value, (dict, list)):
                found.add(normalize_target_id(value))
            else:
                found |= _ids_from(value)
    elif isinstance(payload, list):
        for item in payload:
            found |= _ids_from(item)
    return found


def load_exclusion_ids(sources: Mapping[str, Path | str]) -> tuple[dict[str, list[str]], set[str]]:
    """Kaynak bazında diskalifiye kimliklerini okur; eksik dosya sessiz geçilir.

    Eksik dosya tolere edilir çünkü kapının koşumu, henüz satır dosyası
    üretmemiş bir makinede de (ör. taze bir CI runner) çalışabilmeli; bu bir
    kota genişletme yetkisi değil, yalnızca okuma kolaylığıdır.
    """

    per_source: dict[str, list[str]] = {}
    combined: set[str] = set()
    for name, path in sources.items():
        source = Path(path)
        if not source.is_file():
            per_source[name] = []
            continue
        ids = sorted(_ids_from(json.loads(source.read_text(encoding="utf-8"))))
        per_source[name] = ids
        combined |= set(ids)
    return per_source, combined


def select_holdout(
    cases: Sequence[Mapping[str, Any]],
    *,
    excluded_ids: Iterable[str] = (),
    per_label: int = PER_LABEL,
    seed: int = HOLDOUT_SEED,
    split_seed: int = SPLIT_SEED,
    split: str = "blind_test",
    minimum_per_stratum: int = MINIMUM_CASES_PER_STRATUM,
) -> dict[str, Any]:
    """Kotalara göre donmuş holdout üyelik listesini üretir (offline, deterministik)."""

    excluded = {normalize_target_id(value) for value in excluded_ids}
    rejected: Counter[str] = Counter()
    pools: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    seen: set[str] = set()
    for case in cases:
        target = normalize_target_id(case.get("target_id", ""))
        label = str(case.get("label", ""))
        if label not in LABEL_GROUPS:
            rejected["label_not_holdout_eligible"] += 1
            continue
        if not target:
            rejected["missing_target_id"] += 1
            continue
        if assign_split(target, seed=split_seed) != split:
            rejected[f"not_in_{split}_split"] += 1
            continue
        if target in excluded:
            rejected["used_by_prior_gate"] += 1
            continue
        if target in seen:
            rejected["duplicate_target_id"] += 1
            continue
        seen.add(target)
        stratum = stratum_key(label, str(case.get("reference", "")))
        pools[label][stratum].append(
            {
                "target_id": target,
                "label": label,
                "reference": str(case.get("reference", "")),
                "sectors": [int(item) for item in case.get("sectors", ()) or ()],
                "notes": str(case.get("notes", "")),
                "stratum": stratum,
                "selection_rank": selection_rank(seed, target),
            }
        )

    selected: list[dict[str, Any]] = []
    quotas: dict[str, int] = {}
    pool_sizes: dict[str, int] = {}
    for label, strata in pools.items():
        counts = {key: len(rows) for key, rows in sorted(strata.items())}
        pool_sizes[label] = sum(counts.values())
        allocation = allocate_quotas(counts, per_label, minimum=minimum_per_stratum)
        for stratum, quota in sorted(allocation.items()):
            quotas[stratum] = quota
            ranked = sorted(strata[stratum], key=lambda row: (row["selection_rank"], row["target_id"]))
            selected.extend(ranked[:quota])

    selected.sort(key=lambda row: (row["label"], row["stratum"], row["target_id"]))
    return {
        "schema_version": "1.0",
        "corpus": CAMPAIGN,
        "status": "frozen",
        "materialization": "deterministic_rebuild_from_frozen_sources",
        "split": split,
        "selection": {
            "method": SELECTION_METHOD,
            "seed": seed,
            "split_seed": split_seed,
            "per_label_quota": per_label,
            "minimum_per_stratum": int(minimum_per_stratum),
            "detector_used_for_selection": False,
            "label_groups": {key: list(value) for key, value in sorted(LABEL_GROUPS.items())},
        },
        "floors": {
            "recall": DECLARED_FLOOR_RECALL,
            "false_positive_rate_ceiling": DECLARED_CEILING_FALSE_POSITIVE_RATE,
            "minimum_cases_per_stratum": int(minimum_per_stratum),
            "minimum_evaluated_cases": int(MINIMUM_EVALUATED_CASES),
        },
        "counts": dict(sorted(Counter(row["label"] for row in selected).items())),
        "stratum_counts": dict(sorted(Counter(row["stratum"] for row in selected).items())),
        "pool_sizes": dict(sorted(pool_sizes.items())),
        "quotas": dict(sorted(quotas.items())),
        "rejection_counts": dict(sorted(rejected.items())),
        "holdout_sha256": holdout_sha256(selected),
        "cases": selected,
        "claim_boundary": (
            "External published dispositions (TESS FOP Working Group) on targets that appear in no prior "
            "gate and live in the blind partition of the frozen split. Labels are catalogue dispositions, "
            "not re-adjudicated by this repository. Detection rates measured here transfer to this label "
            "domain and cadence regime only; they are not a survey-wide performance claim and the corpus "
            "was never used to fit or tune anything."
        ),
    }


def holdout_sha256(cases: Sequence[Mapping[str, Any]]) -> str:
    """Üyelik listesinin canonical hash'i (hedef kimliği + katman + etiket)."""

    rows = [
        {
            "target_id": row["target_id"],
            "label": row["label"],
            "stratum": row.get("stratum", stratum_key(row["label"], row.get("reference", ""))),
        }
        for row in cases
    ]
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode()).hexdigest()


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> Optional[list[float]]:
    if total <= 0:
        return None
    phat = successes / total
    denominator = 1.0 + z * z / total
    centre = (phat + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(phat * (1 - phat) / total + z * z / (4 * total * total)) / denominator
    return [round(max(0.0, centre - margin), 6), round(min(1.0, centre + margin), 6)]


def _confusion(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    tp = fp = tn = fn = 0
    for row in rows:
        positive = str(row.get("label")) == "planet"
        detected = bool(row.get("accepted_candidate"))
        if positive and detected:
            tp += 1
        elif positive:
            fn += 1
        elif detected:
            fp += 1
        else:
            tn += 1
    recall = tp / (tp + fn) if (tp + fn) else None
    precision = tp / (tp + fp) if (tp + fp) else None
    false_positive_rate = fp / (fp + tn) if (fp + tn) else None
    return {
        "true_positives": tp,
        "false_negatives": fn,
        "true_negatives": tn,
        "false_positives": fp,
        "recall": None if recall is None else round(recall, 6),
        "precision": None if precision is None else round(precision, 6),
        "false_positive_rate": None if false_positive_rate is None else round(false_positive_rate, 6),
        "wilson_recall_95": wilson_interval(tp, tp + fn),
        "wilson_false_positive_rate_95": wilson_interval(fp, fp + tn),
    }


def build_holdout_report(
    rows: Sequence[Mapping[str, Any]],
    *,
    manifest: Optional[Mapping[str, Any]] = None,
    split_seed: int = SPLIT_SEED,
    split: str = "blind_test",
    floor_recall: float = DECLARED_FLOOR_RECALL,
    ceiling_false_positive_rate: float = DECLARED_CEILING_FALSE_POSITIVE_RATE,
    minimum_evaluated: int = MINIMUM_EVALUATED_CASES,
    minimum_per_stratum: int = MINIMUM_CASES_PER_STRATUM,
    provenance: Optional[Mapping[str, Any]] = None,
    environment: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Satırlardan holdout değerlendirmesi kurar; eşikler önceden ilanlıdır."""

    materialized = [dict(row) for row in rows]
    if not materialized:
        raise ValueError("holdout raporu en az bir değerlendirme satırı gerektirir.")

    evaluated = [row for row in materialized if row.get("accepted_candidate") is not None and not row.get("error")]
    errors = [row for row in materialized if row not in evaluated]
    strata: dict[str, Any] = {}
    for name in sorted({str(row.get("stratum", "unstratified")) for row in materialized}):
        members = [row for row in evaluated if str(row.get("stratum", "unstratified")) == name]
        block = _confusion(members)
        block["n_cases"] = len([row for row in materialized if str(row.get("stratum", "unstratified")) == name])
        block["n_evaluated"] = len(members)
        strata[name] = block

    overall = _confusion(evaluated)
    label_counts = Counter(str(row.get("label")) for row in evaluated)
    non_blind = [
        row
        for row in materialized
        if assign_split(normalize_target_id(row.get("target_id", "")), seed=split_seed) != split
    ]
    corpus_cases = [] if manifest is None else list(manifest.get("cases", []))
    corpus_ids = {normalize_target_id(row.get("target_id", "")) for row in corpus_cases}
    row_ids = {normalize_target_id(row.get("target_id", "")) for row in materialized}
    manifest_sha = None if manifest is None else manifest.get("holdout_sha256")

    blockers: list[str] = []
    if errors:
        blockers.append(f"error_rows:{len(errors)}")
    if len(evaluated) < minimum_evaluated:
        blockers.append(f"evaluated_cases_below_declared_minimum:{len(evaluated)}<{minimum_evaluated}")
    for label in sorted(LABEL_GROUPS):
        if label_counts.get(label, 0) == 0:
            blockers.append(f"label_group_missing:{label}")
    for name, block in strata.items():
        if block["n_evaluated"] < minimum_per_stratum:
            blockers.append(f"stratum_below_minimum:{name}:{block['n_evaluated']}<{minimum_per_stratum}")
    if non_blind:
        blockers.append(f"holdout_not_blind:{len(non_blind)}")
    if overall["recall"] is None or overall["recall"] < floor_recall:
        blockers.append(
            f"recall_below_declared_floor:{'NA' if overall['recall'] is None else overall['recall']}<{floor_recall}"
        )
    if overall["false_positive_rate"] is None or overall["false_positive_rate"] > ceiling_false_positive_rate:
        blockers.append(
            "false_positive_rate_above_declared_ceiling:"
            f"{'NA' if overall['false_positive_rate'] is None else overall['false_positive_rate']}"
            f">{ceiling_false_positive_rate}"
        )
    if manifest is not None:
        if holdout_sha256(corpus_cases) != manifest_sha:
            blockers.append("holdout_manifest_self_inconsistent")
        if row_ids - corpus_ids:
            blockers.append(f"rows_not_in_frozen_corpus:{len(row_ids - corpus_ids)}")
        if corpus_ids - row_ids:
            blockers.append(f"corpus_rows_missing:{len(corpus_ids - row_ids)}")
        if manifest.get("status") != "frozen":
            blockers.append(f"corpus_not_frozen:{manifest.get('status')}")

    return {
        "schema_version": "1.0",
        "campaign": CAMPAIGN,
        "status": "measured" if not blockers else "pending_run",
        "blocking_reasons": blockers,
        "claim_policy": (
            "A gate closes only when its declared status and immutable evidence are measured/pass and "
            "every predeclared acceptance check passes; pending work is never a score."
        ),
        "method": {
            "data": "real_light_curves",
            "label_source": LABELLED_CORPUS,
            "selection_method": SELECTION_METHOD,
            "split": split,
            "split_seed": split_seed,
            "seed": None if manifest is None else manifest.get("selection", {}).get("seed"),
            "detector_used_for_selection": False,
            "detector_stage": "AstroTransitOrchestrator.run_single (detrend -> BLS -> TLS -> vetting)",
            "positive_definition": "a planet-labelled target with at least one confirmed candidate",
            "false_positive_definition": "a false_positive-labelled target with a confirmed candidate",
            "sector_choice": "lowest available SPOC 120s sector at run time (recorded per row)",
            "retrained": False,
            "declared_floor_recall": float(floor_recall),
            "declared_ceiling_false_positive_rate": float(ceiling_false_positive_rate),
            "declared_minimum_evaluated_cases": int(minimum_evaluated),
            "declared_minimum_cases_per_stratum": int(minimum_per_stratum),
        },
        "corpus": {
            "sha256": manifest_sha,
            "recomputed_sha256": None if manifest is None else holdout_sha256(corpus_cases),
            "n_rows": len(materialized),
            "n_cases": None if manifest is None else len(corpus_cases),
            "counts": dict(sorted(label_counts.items())),
            "stratum_counts": None if manifest is None else manifest.get("stratum_counts"),
            "n_rows_not_in_corpus": len(row_ids - corpus_ids),
            "n_missing_rows": len(corpus_ids - row_ids),
        },
        "data": {
            "n_rows": len(materialized),
            "n_evaluated": len(evaluated),
            "errors": len(errors),
            "sector_fetch_failures": sum(1 for row in materialized if row.get("successful_sector_count", 0) == 0),
        },
        "disjointness": {
            "split": split,
            "non_blind_rows": len(non_blind),
            "exclusion_sources": None
            if manifest is None
            else sorted((manifest.get("exclusions") or {}).get("sources", {})),
            "excluded_id_count": None
            if manifest is None
            else sum(len(values) for values in ((manifest.get("exclusions") or {}).get("sources", {}) or {}).values()),
        },
        "overall": overall,
        "strata": strata,
        "environment": dict(environment or {}),
        "provenance": dict(provenance or {}),
        "claim_boundary": (
            "Real TESS targets with external FOP WG dispositions, drawn only from the blind partition and "
            "from targets no prior gate has touched. Because sectors are chosen at run time and no model "
            "was fitted on these targets, the measured recall/false-positive rate describes this label "
            "domain and cadence regime; it is not a survey-wide performance estimate and not a statement "
            "about any individual target."
        ),
    }


__all__ = [
    "CAMPAIGN",
    "DECLARED_CEILING_FALSE_POSITIVE_RATE",
    "DECLARED_FLOOR_RECALL",
    "FP_RUN_SUBSET",
    "GATE_ID",
    "HOLDOUT_MANIFEST",
    "HOLDOUT_SEED",
    "LABELLED_CORPUS",
    "LABEL_GROUPS",
    "MINIMUM_CASES_PER_STRATUM",
    "MINIMUM_EVALUATED_CASES",
    "PRIOR_INJECTION_HOSTS",
    "REQUIRED_OUTPUT",
    "SELECTION_METHOD",
    "SPLIT_SEED",
    "allocate_quotas",
    "build_holdout_report",
    "disposition_code",
    "holdout_sha256",
    "load_exclusion_ids",
    "normalize_target_id",
    "select_holdout",
    "selection_rank",
    "stratum_key",
    "wilson_interval",
]
