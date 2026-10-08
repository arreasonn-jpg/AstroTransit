"""Build a confusion matrix from adversarial FP rows.jsonl."""

import json
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    rows_path = Path("validation_runs/final_acceptance_v1/adversarial_fp/rows.jsonl")
    if not rows_path.exists():
        print(f"ERROR: {rows_path} not found", file=sys.stderr)
        return 1

    rows = []
    with rows_path.open() as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    # Determine expected (FP vs planet) from family
    # We know planetary_control is the only "planet" family
    PLANET_FAMILIES = {"planetary_control"}
    REJECT_OUTCOMES = {
        "rejected_at_detection",
        "rejected_at_cascade",
        "rejected_at_vetting",
        "rejected_at_anomaly",
    }
    LEAK = "leaked_as_candidate"

    # 2x2 matrix
    matrix = Counter()
    for r in rows:
        fam = str(r.get("family", ""))
        expected = "planet" if fam in PLANET_FAMILIES else "fp"
        outcome = str(r.get("outcome", ""))
        if outcome in REJECT_OUTCOMES:
            predicted = "fp"  # rejected = predicted FP
        elif outcome == LEAK:
            predicted = "planet"  # accepted = predicted planet
        else:
            continue  # skip errors
        matrix[(expected, predicted)] += 1

    TP = matrix[("fp", "fp")]       # correctly rejected FP
    FN = matrix[("fp", "planet")]   # FP leaked
    TN = matrix[("planet", "planet")]  # correctly accepted planet
    FP = matrix[("planet", "fp")]   # planet rejected (bad)

    # Compute metrics
    total = TP + FN + TN + FP
    specificity = TP / (TP + FN) if (TP + FN) > 0 else None
    sensitivity = TN / (TN + FP) if (TN + FP) > 0 else None  # this is "recall of planets"
    balanced_acc = (specificity + sensitivity) / 2 if (specificity is not None and sensitivity is not None) else None
    precision = TP / (TP + FP) if (TP + FP) > 0 else None
    fpr = FP / (FP + TN) if (FP + TN) > 0 else None  # FP rate on planets
    fnr = FN / (FN + TP) if (FN + TP) > 0 else None  # miss rate on FP

    result = {
        "matrix": {
            "true_fp_predicted_fp": TP,
            "true_fp_predicted_planet": FN,
            "true_planet_predicted_planet": TN,
            "true_planet_predicted_fp": FP,
            "total": total,
        },
        "metrics": {
            "fp_specificity": round(specificity, 4) if specificity is not None else None,
            "planet_recall": round(sensitivity, 4) if sensitivity is not None else None,
            "balanced_accuracy": round(balanced_acc, 4) if balanced_acc is not None else None,
            "precision": round(precision, 4) if precision is not None else None,
            "fpr_on_planets": round(fpr, 4) if fpr is not None else None,
            "fnr_on_fp": round(fnr, 4) if fnr is not None else None,
        },
    }

    # Print
    print("=== Confusion Matrix ===")
    print("                 Predicted FP    Predicted Planet")
    print(f"Actual FP        {TP:5d}           {FN:5d}")
    print(f"Actual Planet    {FP:5d}           {TN:5d}")
    print()
    print("Metrics:")
    for k, v in result["metrics"].items():
        print(f"  {k:20s} {v}")

    out = Path("validation_runs/final_acceptance_v1/adversarial_fp/confusion_matrix.json")
    out.write_text(json.dumps(result, indent=2))
    print()
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
