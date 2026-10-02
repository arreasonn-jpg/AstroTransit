"""Takip gözlemleri, benchmark raporları ve doğrulama sözleşmeleri."""

from astrotransit.validation.adapters import (
    RVFollowupMeasurement,
    TransitFollowupMeasurement,
    rv_measurement_to_evidence,
    transit_measurement_to_evidence,
)
from astrotransit.validation.adversarial_fp import (
    ADVERSARIAL_FAMILIES,
    ADVERSARIAL_FPP_REJECT_THRESHOLD,
    AdversarialScenario,
    build_adversarial_report,
    classify_outcome,
    grid_sha256,
    synthetic_lightcurve,
)
from astrotransit.validation.artifacts import write_artifact
from astrotransit.validation.baselines import (
    BaselineComparison,
    BaselineMeasurement,
    compare_baselines,
)
from astrotransit.validation.benchmark_report import (
    BenchmarkPerformanceReport,
    BenchmarkTargetMeasurement,
    VerifiedTarget,
    evaluate_benchmark_results,
    load_verified_targets,
    normalize_target_id,
)
from astrotransit.validation.blind_holdout import (
    SELECTION_METHOD as BLIND_HOLDOUT_SELECTION_METHOD,
)
from astrotransit.validation.blind_holdout import (
    allocate_quotas,
    build_holdout_report,
    holdout_sha256,
    select_holdout,
)
from astrotransit.validation.claims import (
    ClaimEvidenceError,
    ClaimStatus,
    infer_claim_status,
    validate_claim,
)
from astrotransit.validation.corpus import ALLOWED_LABELS, CorpusCase, corpus_summary, load_corpus
from astrotransit.validation.corpus_evaluation import CorpusEvaluation, evaluate_corpus
from astrotransit.validation.cross_sector import CrossSectorReport, assess_cross_sector_consistency
from astrotransit.validation.determinism import assert_deterministic, canonical_json, output_hash
from astrotransit.validation.failures import FailureCode, classify_failure, failure_codes_as_json
from astrotransit.validation.followup import (
    FOLLOWUP_OBSERVATION_TYPES,
    FollowupEvidence,
    FollowupValidationResult,
    coerce_followup_result,
    validate_followup_evidence,
)
from astrotransit.validation.fpp_benchmark import (
    FPPBenchmarkCase,
    FPPBenchmarkReport,
    evaluate_fpp_benchmark,
    evaluate_fpp_holdout,
    split_fpp_cases,
)
from astrotransit.validation.fpp_calibration import (
    FPP_CALIBRATION_CAMPAIGN,
    FPP_CALIBRATION_SEED,
    FPP_CALIBRATION_THRESHOLD,
    MIN_BLIND_TEST_ROC_AUC,
    MIN_FPP_CASES_PER_COHORT,
    build_fpp_calibration_report,
)
from astrotransit.validation.fpp_telemetry import (
    FPP_TELEMETRY_VERSION,
    adopt_target_fpp,
    attach_row_fpp,
    read_row_fpp,
    sector_fpp_telemetry,
)
from astrotransit.validation.injection_recovery import (
    InjectionRecoveryReport,
    InjectionScenario,
    RecoveryTrial,
    inject_box_transit,
    make_injection_grid,
    run_injection_recovery,
)
from astrotransit.validation.metrics import RecoveryMetric, interval_coverage, parameter_recovery
from astrotransit.validation.performance import RuntimeMeasurement, measure_runtime
from astrotransit.validation.plots import generate_validation_figures
from astrotransit.validation.provenance import (
    attach_manifest,
    build_manifest,
    canonical_hash,
    sha256_file,
)
from astrotransit.validation.release_gate import (
    GateResult,
    ReleaseGateReport,
    evaluate_release_gates,
)
from astrotransit.validation.sensitivity import (
    SimilaritySensitivityReport,
    earth_similarity_sensitivity,
)
from astrotransit.validation.splits import assign_split, partition_target_ids

__all__ = [
    "ADVERSARIAL_FAMILIES",
    "ADVERSARIAL_FPP_REJECT_THRESHOLD",
    "ALLOWED_LABELS",
    "BLIND_HOLDOUT_SELECTION_METHOD",
    "FOLLOWUP_OBSERVATION_TYPES",
    "FPP_CALIBRATION_CAMPAIGN",
    "FPP_CALIBRATION_SEED",
    "FPP_CALIBRATION_THRESHOLD",
    "FPP_TELEMETRY_VERSION",
    "MIN_BLIND_TEST_ROC_AUC",
    "MIN_FPP_CASES_PER_COHORT",
    "AdversarialScenario",
    "BaselineComparison",
    "BaselineMeasurement",
    "BenchmarkPerformanceReport",
    "BenchmarkTargetMeasurement",
    "ClaimEvidenceError",
    "ClaimStatus",
    "CorpusCase",
    "CorpusEvaluation",
    "CrossSectorReport",
    "FPPBenchmarkCase",
    "FPPBenchmarkReport",
    "FailureCode",
    "FollowupEvidence",
    "FollowupValidationResult",
    "GateResult",
    "InjectionRecoveryReport",
    "InjectionScenario",
    "RVFollowupMeasurement",
    "RecoveryMetric",
    "RecoveryTrial",
    "ReleaseGateReport",
    "RuntimeMeasurement",
    "SimilaritySensitivityReport",
    "TransitFollowupMeasurement",
    "VerifiedTarget",
    "adopt_target_fpp",
    "allocate_quotas",
    "assert_deterministic",
    "assess_cross_sector_consistency",
    "assign_split",
    "attach_manifest",
    "attach_row_fpp",
    "build_adversarial_report",
    "build_fpp_calibration_report",
    "build_holdout_report",
    "build_manifest",
    "canonical_hash",
    "canonical_json",
    "classify_failure",
    "classify_outcome",
    "coerce_followup_result",
    "compare_baselines",
    "corpus_summary",
    "earth_similarity_sensitivity",
    "evaluate_benchmark_results",
    "evaluate_corpus",
    "evaluate_fpp_benchmark",
    "evaluate_fpp_holdout",
    "evaluate_release_gates",
    "failure_codes_as_json",
    "generate_validation_figures",
    "grid_sha256",
    "holdout_sha256",
    "infer_claim_status",
    "inject_box_transit",
    "interval_coverage",
    "load_corpus",
    "load_verified_targets",
    "make_injection_grid",
    "measure_runtime",
    "normalize_target_id",
    "output_hash",
    "parameter_recovery",
    "partition_target_ids",
    "read_row_fpp",
    "run_injection_recovery",
    "rv_measurement_to_evidence",
    "sector_fpp_telemetry",
    "select_holdout",
    "sha256_file",
    "split_fpp_cases",
    "synthetic_lightcurve",
    "transit_measurement_to_evidence",
    "validate_claim",
    "validate_followup_evidence",
    "write_artifact",
]
