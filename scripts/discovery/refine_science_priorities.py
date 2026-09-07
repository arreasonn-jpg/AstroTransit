from pathlib import Path
import pandas as pd

project_root = Path(__file__).resolve().parents[2]

IN_PATH = project_root / "outputs_discovery" / "novel_candidates_prioritized.parquet"
OUT_PARQUET = project_root / "outputs_discovery" / "novel_candidates_science_prioritized.parquet"
OUT_CSV = project_root / "outputs_discovery" / "novel_candidates_science_prioritized.csv"


def as_bool(v):
    if pd.isna(v):
        return False
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in {"true", "1", "yes", "y"}
    return bool(v)


def text(v):
    if pd.isna(v):
        return ""
    return str(v)


def classify(row):
    rp = row.get("planet_radius_rearth", 0) or 0
    teq = row.get("equilibrium_temperature_k", 0) or 0
    snr = row.get("snr_adopted", 0) or 0
    period = row.get("period", 0) or 0
    n_transits = row.get("n_transits", 0) or 0
    discovery_priority = text(row.get("discovery_priority", ""))
    discovery_reason = text(row.get("discovery_reason", ""))
    candidate_class = text(row.get("candidate_class", ""))
    is_fp = as_bool(row.get("is_false_positive", False))
    is_bin = as_bool(row.get("is_binary_suspect", False))
    is_anom = as_bool(row.get("is_anomalous", False))
    anomaly_flags = text(row.get("anomaly_flags", ""))
    odd_even = row.get("tls_odd_even_mismatch", None)

    reasons = []
    score = 0

    if period <= 0:
        return "LOW_PRIORITY", 0, "invalid period"
    if rp <= 0:
        return "LOW_PRIORITY", 0, "invalid radius"
    if is_fp:
        return "LOW_PRIORITY", 0, "false positive flag"
    if "radius too large" in discovery_reason.lower():
        return "LOW_PRIORITY", 0, "radius too large"

    if discovery_priority == "FOLLOWUP":
        score += 25
        reasons.append("followup")
    elif discovery_priority == "WATCHLIST":
        score += 10
        reasons.append("watchlist")

    if candidate_class == "A":
        score += 20
        reasons.append("class A")
    elif candidate_class == "C":
        score += 5
        reasons.append("class C")

    if snr >= 20:
        score += 20
        reasons.append("snr>=20")
    elif snr >= 10:
        score += 15
        reasons.append("snr>=10")
    elif snr >= 7.5:
        score += 10
        reasons.append("snr>=7.5")
    elif snr >= 5.5:
        score += 5
        reasons.append("snr>=5.5")

    if n_transits >= 5:
        score += 10
        reasons.append("multi-transit")
    elif n_transits >= 3:
        score += 5
        reasons.append("3+ transits")

    if is_bin:
        score -= 30
        reasons.append("binary-suspect")

    if odd_even is not None and not pd.isna(odd_even):
        if odd_even >= 3:
            score -= 20
            reasons.append("high odd-even mismatch")
        elif odd_even >= 1.5:
            score -= 8
            reasons.append("moderate odd-even mismatch")

    if (
        rp <= 2.2 and
        teq > 0 and teq <= 1100 and
        snr >= 7.5 and
        not is_bin and
        (pd.isna(odd_even) or odd_even < 3)
    ):
        score += 25
        reasons.append("small-cool-core")
        return "SMALL_COOL_CORE", score, "; ".join(reasons)

    if (
        rp <= 2.0 and
        teq > 0 and teq <= 1100 and
        snr >= 5.5 and
        not is_bin
    ):
        score += 15
        reasons.append("small-cool-second-look")
        return "SMALL_COOL_SECOND_LOOK", score, "; ".join(reasons)

    if (
        rp <= 2.8 and
        teq > 1100 and
        snr >= 7 and
        not is_bin
    ):
        score += 12
        reasons.append("small-hot")
        return "SMALL_HOT", score, "; ".join(reasons)

    if (
        snr >= 10 and
        n_transits >= 3 and
        (is_anom or anomaly_flags.strip() != "")
    ):
        score += 10
        reasons.append("anomaly-review")
        return "ANOMALY_REVIEW", score, "; ".join(reasons)

    if discovery_priority == "FOLLOWUP":
        score += 5
        reasons.append("standard-followup")
        return "STANDARD_FOLLOWUP", score, "; ".join(reasons)

    return "LOW_PRIORITY", score, "; ".join(reasons) if reasons else "no priority rule matched"


def main():
    if not IN_PATH.exists():
        print(f"Girdi bulunamadi: {IN_PATH}")
        raise SystemExit(1)

    df = pd.read_parquet(IN_PATH)

    buckets = []
    scores = []
    reasons = []

    for _, row in df.iterrows():
        bucket, score, reason = classify(row)
        buckets.append(bucket)
        scores.append(score)
        reasons.append(reason)

    df["science_priority_bucket"] = buckets
    df["science_priority_score"] = scores
    df["science_priority_reason"] = reasons

    df = df.sort_values(
        ["science_priority_bucket", "science_priority_score", "snr_adopted"],
        ascending=[True, False, False]
    )

    OUT_PARQUET.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT_PARQUET, index=False)
    df.to_csv(OUT_CSV, index=False)

    print("=" * 72)
    print("Science Priority Refinement")
    print("=" * 72)
    print(df["science_priority_bucket"].value_counts())
    print()
    cols = [c for c in [
        "source_id",
        "sector",
        "period",
        "planet_radius_rearth",
        "equilibrium_temperature_k",
        "snr_adopted",
        "candidate_class",
        "discovery_priority",
        "science_priority_bucket",
        "science_priority_score",
        "science_priority_reason",
    ] if c in df.columns]
    print(df[cols].head(40).to_string(index=False))
    print()
    print(f"CSV: {OUT_CSV}")
    print(f"Parquet: {OUT_PARQUET}")
    print("=" * 72)


if __name__ == "__main__":
    main()
