"""Publication-oriented validation figure generation from immutable reports."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping


def generate_validation_figures(report: Mapping[str, Any], output_dir: str | Path) -> list[Path]:
    """Generate available figures; absent metrics produce no fabricated plot."""
    import matplotlib.pyplot as plt

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    metadata = report.get("metadata", {})
    targets = report.get("targets", [])
    period_rows = [(row.get("expected_period_days"), row.get("recovered_period_days"))
                   for row in targets if row.get("expected_period_days") is not None and row.get("recovered_period_days") is not None]
    if period_rows:
        figure, axis = plt.subplots()
        x, y = zip(*period_rows)
        axis.scatter(x, y, s=18)
        axis.plot([min(x), max(x)], [min(x), max(x)], "k--", linewidth=.8)
        axis.set(xlabel="Expected period (days)", ylabel="Recovered period (days)", title="Injected/expected vs recovered period")
        path = destination / "period_recovery.png"
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)
    calibration = report.get("calibration_curve", [])
    if calibration:
        figure, axis = plt.subplots()
        axis.plot([0, 1], [0, 1], "k--", linewidth=.8)
        axis.plot([row["mean_predicted"] for row in calibration], [row["observed_rate"] for row in calibration], "o-")
        axis.set(xlabel="Predicted false-positive risk", ylabel="Observed false-positive rate", title="FPP reliability")
        path = destination / "fpp_reliability.png"
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)
    manifest = destination / "figure_manifest.json"
    import json
    manifest.write_text(json.dumps({"source_metadata": metadata, "figures": [str(path.name) for path in paths]}, indent=2) + "\n", encoding="utf-8")
    return paths


__all__ = ["generate_validation_figures"]
