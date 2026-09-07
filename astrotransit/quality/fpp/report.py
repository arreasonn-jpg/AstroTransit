"""
Simple FPP rapor yazım / render modülü.

Amaç
----
SimpleFPPReport nesnesini:
- metin raporuna
- JSON dosyasına
- birlikte sidecar bundle'a

dönüştürmek.

Bu modül hesaplama yapmaz; yalnızca çıktı üretir.
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import Optional

from loguru import logger

from astrotransit.quality.fpp.calculator import SimpleFPPReport


class FPPReportWriter:
    """
    Simple FPP rapor yazıcısı.
    """

    def __init__(self, indent: int = 2):
        self.indent = indent
        logger.debug("FPPReportWriter başlatıldı.")

    def render_text(
        self,
        report: SimpleFPPReport,
    ) -> str:
        """
        İnsan-okunur metin raporu üretir.
        """

        lines: list[str] = []
        lines.append("Simple FPP Report")
        lines.append("=" * 72)
        lines.append(f"Target           : {report.target_id}")
        lines.append(f"Sector           : {report.sector}")
        lines.append(f"FPP              : {report.fpp:.4f}")
        lines.append(f"P(planet)        : {report.p_planet:.4f}")
        lines.append(f"Dominant scenario: {report.dominant_scenario}")
        lines.append(f"Confidence       : {report.confidence}")
        lines.append(f"Recommended      : {report.recommended_action}")
        lines.append(f"Available comps  : {report.n_available}")
        lines.append("")

        lines.append("Scenario probabilities")
        lines.append("-" * 72)
        lines.append(f"EB   : {report.p_eb:.4f}")
        lines.append(f"BEB  : {report.p_beb:.4f}")
        lines.append(f"NEB  : {report.p_neb:.4f}")
        lines.append("")

        lines.append("Components")
        lines.append("-" * 72)
        if report.components:
            for comp in report.components:
                prob = "None" if comp.probability is None else f"{comp.probability:.4f}"
                lines.append(
                    f"- {comp.name.upper():<4} "
                    f"available={comp.available!s:<5} "
                    f"prob={prob:<7} "
                    f"flag={comp.risk_flag:<20} "
                    f"action={comp.recommended_action}"
                )
        else:
            lines.append("- No components available")
        lines.append("")

        if report.details:
            lines.append("Details")
            lines.append("-" * 72)
            for key, value in report.details.items():
                lines.append(f"{key}: {value}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def build_payload(
        self,
        report: SimpleFPPReport,
    ) -> dict:
        """
        JSON serileştirme için payload döndürür.
        """
        return report.to_dict()

    def write_json(
        self,
        report: SimpleFPPReport,
        path: str | Path,
    ) -> Path:
        """
        JSON dosyasına yazar.
        """

        outpath = Path(path)
        outpath.parent.mkdir(parents=True, exist_ok=True)

        payload = self.build_payload(report)

        with outpath.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=self.indent)

        logger.info(f"FPP JSON yazıldı: {outpath}")
        return outpath

    def write_text(
        self,
        report: SimpleFPPReport,
        path: str | Path,
    ) -> Path:
        """
        Metin raporunu dosyaya yazar.
        """

        outpath = Path(path)
        outpath.parent.mkdir(parents=True, exist_ok=True)

        text = self.render_text(report)

        with outpath.open("w", encoding="utf-8") as f:
            f.write(text)

        logger.info(f"FPP metin raporu yazıldı: {outpath}")
        return outpath

    def write_bundle(
        self,
        report: SimpleFPPReport,
        output_dir: str | Path,
        stem: Optional[str] = None,
    ) -> dict[str, str]:
        """
        JSON + text bundle yazar.

        Returns
        -------
        dict
            Yazılan dosya yolları.
        """

        outdir = Path(output_dir)
        outdir.mkdir(parents=True, exist_ok=True)

        if stem is None:
            safe_target = (
                str(report.target_id)
                .replace(" ", "_")
                .replace("/", "_")
                .replace("\\", "_")
            )
            stem = f"{safe_target}_S{report.sector}_simple_fpp"

        json_path = outdir / f"{stem}.json"
        txt_path = outdir / f"{stem}.txt"

        self.write_json(report, json_path)
        self.write_text(report, txt_path)

        bundle = {
            "json": str(json_path),
            "text": str(txt_path),
        }

        logger.info(f"FPP bundle yazıldı: {bundle}")
        return bundle
