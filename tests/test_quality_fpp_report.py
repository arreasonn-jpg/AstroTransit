"""astrotransit/quality/fpp/report.py için testler."""
from __future__ import annotations

import json
from types import SimpleNamespace

from astrotransit.quality.fpp.report import FPPReportWriter


def _make_report(**over):
    comp = SimpleNamespace(
        name="eb", available=True, probability=0.05,
        risk_flag="LOW_EB_RISK", recommended_action="no_action",
    )
    base = dict(
        target_id="TIC 123", sector=14,
        fpp=0.05, p_planet=0.95, fpp_method="heuristic_v1",
        dominant_scenario="PLANET", confidence="HIGH",
        recommended_action="follow_up",
        n_available=3,
        p_eb=0.05, p_beb=0.03, p_neb=0.02,
        components=[comp],
        details={"note": "test"},
    )
    base.update(over)
    return SimpleNamespace(**{
        **base, "to_dict": lambda: {"target_id": base["target_id"], "fpp": base["fpp"]},
    })


def test_init():
    w = FPPReportWriter()
    assert w.indent == 2
    w2 = FPPReportWriter(indent=4)
    assert w2.indent == 4


def test_render_text_contains_all_fields():
    w = FPPReportWriter()
    text = w.render_text(_make_report())
    assert "TIC 123" in text
    assert "Sector" in text
    assert "0.0500" in text
    assert "PLANET" in text
    assert "HIGH" in text
    assert "EB" in text  # component name (render'da upper case)


def test_render_text_none_values():
    w = FPPReportWriter()
    text = w.render_text(_make_report(
        fpp=None, p_planet=None, p_eb=None, p_beb=None, p_neb=None,
    ))
    assert "not_available" in text


def test_render_text_no_components():
    w = FPPReportWriter()
    text = w.render_text(_make_report(components=[]))
    assert "No components available" in text


def test_render_text_no_details():
    w = FPPReportWriter()
    text = w.render_text(_make_report(details={}))
    assert "Details" not in text


def test_build_payload():
    w = FPPReportWriter()
    payload = w.build_payload(_make_report())
    assert payload["target_id"] == "TIC 123"


def test_write_json(tmp_path):
    w = FPPReportWriter()
    out = w.write_json(_make_report(), tmp_path / "sub" / "r.json")
    assert out.exists()
    data = json.loads(out.read_text())
    assert data["target_id"] == "TIC 123"


def test_write_text(tmp_path):
    w = FPPReportWriter()
    out = w.write_text(_make_report(), tmp_path / "sub" / "r.txt")
    assert out.exists()
    assert "TIC 123" in out.read_text()


def test_write_bundle_default_stem(tmp_path):
    w = FPPReportWriter()
    bundle = w.write_bundle(_make_report(), tmp_path / "out")
    assert bundle["json"].endswith(".json")
    assert bundle["text"].endswith(".txt")
    assert "TIC_123" in bundle["json"]
    assert "S14" in bundle["json"]
    assert "simple_fpp" in bundle["json"]


def test_write_bundle_custom_stem(tmp_path):
    w = FPPReportWriter()
    bundle = w.write_bundle(_make_report(), tmp_path / "out", stem="custom")
    assert "custom.json" in bundle["json"]
    assert "custom.txt" in bundle["text"]


def test_write_bundle_safe_target_id(tmp_path):
    w = FPPReportWriter()
    bundle = w.write_bundle(
        _make_report(target_id="a/b\\c d"), tmp_path / "out",
    )
    assert "a_b_c_d" in bundle["json"]
