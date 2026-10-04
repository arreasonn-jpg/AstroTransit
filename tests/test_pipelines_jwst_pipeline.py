"""astrotransit/pipelines/jwst_pipeline.py için testler."""
from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from astrotransit.pipelines.jwst_pipeline import (
    JWSTFollowUpPipeline,
    JWSTFollowUpResult,
    JWSTObservationResult,
    JWSTProductContract,
    JWSTProductValidation,
    load_jwst_product,
)

# ═══════════════════════════════════════════════════════
# JWSTProductContract
# ═══════════════════════════════════════════════════════

def _contract(**over):
    base = dict(
        product_path="dummy.fits",
        target_id="WASP-39",
        obs_id="obs1",
        program_id="1234",
        instrument="NIRSpec",
    )
    base.update(over)
    return JWSTProductContract(**base)


def test_contract_validate_ok():
    c = _contract()
    c.validate()  # raise etmemeli


def test_contract_validate_missing_target():
    with pytest.raises(ValueError, match="target_id"):
        _contract(target_id="").validate()


def test_contract_validate_missing_program():
    with pytest.raises(ValueError, match="program_id"):
        _contract(program_id="").validate()


def test_contract_validate_bad_level():
    with pytest.raises(ValueError, match="data_level"):
        _contract(data_level="stage1").validate()


def test_contract_validate_missing_flux_column():
    with pytest.raises(ValueError, match="time ve flux"):
        _contract(flux_column="").validate()


# ═══════════════════════════════════════════════════════
# JWSTProductValidation
# ═══════════════════════════════════════════════════════

def test_validation_to_dict():
    v = JWSTProductValidation(
        valid=True, product_path="x.fits", n_points=100,
        columns=("TIME", "FLUX"),
    )
    d = v.to_dict()
    assert d["valid"] is True
    assert d["n_points"] == 100
    assert d["columns"] == ["TIME", "FLUX"]


# ═══════════════════════════════════════════════════════
# load_jwst_product
# ═══════════════════════════════════════════════════════

def test_load_missing_file():
    c = _contract(product_path="/nonexistent/file.fits")
    obs, val = load_jwst_product(c)
    assert obs is None
    assert val.valid is False
    assert "FileNotFoundError" in val.error or "bulunamadı" in val.error.lower()


def test_load_invalid_contract():
    c = _contract(target_id="")
    obs, val = load_jwst_product(c)
    assert obs is None
    assert val.valid is False


def test_load_happy_with_fake_fits(tmp_path):
    fake_file = tmp_path / "product.fits"
    fake_file.write_bytes(b"fake")

    # Fake astropy.io.fits
    class _FakeData:
        def __init__(self):
            self.names = ["TIME", "FLUX", "FLUX_ERR"]
        def __getitem__(self, name):
            n = 50
            if name == "TIME":
                return np.linspace(0, 1, n)
            if name == "FLUX":
                return np.ones(n)
            return np.full(n, 1e-4)

    class _FakeHDU:
        data = _FakeData()
        header: ClassVar[dict] = {"TARGNAME": "WASP-39", "INSTRUME": "NIRSpec"}

    class _FakeHDUList:
        def __init__(self): self._list = [_FakeHDU()]
        def __iter__(self): return iter(self._list)
        def __enter__(self): return self
        def __exit__(self, *a): return False

    fake_fits = SimpleNamespace(open=lambda p, memmap=False: _FakeHDUList())

    with patch.dict("sys.modules", {"astropy.io.fits": fake_fits}), \
         patch("astropy.io.fits.open", fake_fits.open, create=True):
        # astropy.io.fits modülü zaten kurulu, open'ı patch'leyelim
        import astropy.io.fits as real_fits
        with patch.object(real_fits, "open", fake_fits.open):
            c = _contract(product_path=str(fake_file))
            obs, val = load_jwst_product(c)
    assert val.valid is True
    assert obs is not None
    assert obs.n_points == 50


def test_load_missing_columns(tmp_path):
    fake_file = tmp_path / "product.fits"
    fake_file.write_bytes(b"fake")

    class _FakeData:
        names: ClassVar[list] = ["FOO", "BAR"]
        def __getitem__(self, name): return np.ones(10)

    class _FakeHDU:
        data = _FakeData()
        header: ClassVar[dict] = {}

    class _FakeHDUList:
        def __iter__(self): return iter([_FakeHDU()])
        def __enter__(self): return self
        def __exit__(self, *a): return False

    import astropy.io.fits as real_fits
    with patch.object(real_fits, "open", lambda *a, **k: _FakeHDUList()):
        obs, val = load_jwst_product(_contract(product_path=str(fake_file)))
    assert obs is None
    assert val.valid is False


# ═══════════════════════════════════════════════════════
# JWSTFollowUpResult
# ═══════════════════════════════════════════════════════

def test_result_summary():
    r = JWSTFollowUpResult(target_id="WASP-39", tess_period=4.05)
    s = r.summary()
    assert s["target_id"] == "WASP-39"
    assert s["tess_period"] == 4.05


def test_result_to_followup_evidence_no_confirm():
    r = JWSTFollowUpResult(target_id="WASP-39", tess_period=4.05)
    ev = r.to_followup_evidence()
    assert ev.source == "JWST"
    assert ev.confirmed is False


def test_result_to_followup_evidence_requires_transit():
    r = JWSTFollowUpResult(target_id="WASP-39")
    with pytest.raises(ValueError, match="transit"):
        r.to_followup_evidence(confirmed=True)


def test_result_to_followup_evidence_with_confirmed_transit():
    obs = JWSTObservationResult(
        program_id="1234", instrument="NIRSpec",
        observation_id="obs1", success=True, transit_confirmed=True,
    )
    r = JWSTFollowUpResult(target_id="WASP-39", results=[obs])
    ev = r.to_followup_evidence(confirmed=True, mass_mearth=10.0)
    assert ev.confirmed is True
    assert ev.mass_mearth == 10.0


# ═══════════════════════════════════════════════════════
# JWSTObservationResult
# ═══════════════════════════════════════════════════════

def test_obs_result_defaults():
    r = JWSTObservationResult()
    assert r.success is False
    assert r.transit_confirmed is False
    assert r.error == ""
    assert r.noise_ppm == 0.0


# ═══════════════════════════════════════════════════════
# JWSTFollowUpPipeline
# ═══════════════════════════════════════════════════════

def _patch_pipeline(monkeypatch):
    import astrotransit.pipelines.jwst_pipeline as mod
    monkeypatch.setattr(mod, "MASTClient", lambda: MagicMock())
    monkeypatch.setattr(mod, "JWSTGPDetrending", lambda **kw: MagicMock())
    monkeypatch.setattr(mod, "MAPFitter", lambda **kw: MagicMock())


def test_pipeline_init(monkeypatch):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()
    assert p._mast is not None
    assert p._gp_detrend is not None
    assert p._map_fitter is not None


def test_search_jwst_observations_happy(monkeypatch):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()
    p._mast.query_observations.return_value = [
        {"obs_id": "o1", "target_name": "W39", "instrument_name": "NIRSpec",
         "filters": "F150W", "t_min": 1.0, "t_max": 2.0, "proposal_id": "1234"}
    ]
    results = p.search_jwst_observations("WASP-39")
    assert len(results) == 1
    assert results[0]["obs_id"] == "o1"


def test_search_jwst_observations_mast_error(monkeypatch):
    _patch_pipeline(monkeypatch)
    from astrotransit.data.mast_client import MASTConnectionError
    p = JWSTFollowUpPipeline()
    p._mast.query_observations.side_effect = MASTConnectionError("net")
    results = p.search_jwst_observations("WASP-39")
    assert results == []


def test_run_no_observations(monkeypatch):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()
    p.search_jwst_observations = MagicMock(return_value=[])
    r = p.run(
        "WASP-39", tess_period=4.05, tess_t0=2459000.0,
        tess_duration=0.1, tess_rp_rs=0.1,
    )
    assert r.success is False
    assert "bulunamadı" in r.error


def test_run_happy_path(monkeypatch):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()
    p.search_jwst_observations = MagicMock(return_value=[{"obs_id": "o1"}])

    def fake_process(**kw):
        return JWSTObservationResult(
            program_id="1234", instrument="NIRSpec",
            observation_id="o1", success=True, noise_ppm=100.0,
        )
    p._process_observation = MagicMock(side_effect=fake_process)

    r = p.run(
        "WASP-39", tess_period=4.05, tess_t0=2459000.0,
        tess_duration=0.1, tess_rp_rs=0.1,
    )
    assert r.success is True
    assert r.observations_processed == 1


def test_run_handles_process_exception(monkeypatch):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()
    p.search_jwst_observations = MagicMock(return_value=[{"obs_id": "o1"}])
    p._process_observation = MagicMock(side_effect=RuntimeError("boom"))
    r = p.run(
        "WASP-39", tess_period=4.05, tess_t0=2459000.0,
        tess_duration=0.1, tess_rp_rs=0.1,
    )
    assert r.success is False


def test_process_product_missing_file(monkeypatch):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()
    c = _contract(product_path="/nonexistent/x.fits")
    r = p.process_product(c)
    assert r.success is False
    assert r.product_validation is not None
    assert r.product_validation["valid"] is False


def test_process_product_detrend_failure(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()

    # load_jwst_product'i başarılı mockla
    fake_obs = MagicMock()
    import astrotransit.pipelines.jwst_pipeline as mod
    monkeypatch.setattr(
        mod, "load_jwst_product",
        lambda c: (fake_obs, JWSTProductValidation(
            valid=True, product_path="x.fits", n_points=100)),
    )
    p._gp_detrend.detrend.side_effect = RuntimeError("gp fail")

    r = p.process_product(_contract(product_path=str(tmp_path / "x.fits")))
    assert r.success is False
    assert "detrending" in r.error


def test_process_product_happy(monkeypatch, tmp_path):
    _patch_pipeline(monkeypatch)
    p = JWSTFollowUpPipeline()

    fake_obs = MagicMock()
    fake_detrended = SimpleNamespace(noise_ppm=42.0)
    p._gp_detrend.detrend.return_value = fake_detrended

    import astrotransit.pipelines.jwst_pipeline as mod
    monkeypatch.setattr(
        mod, "load_jwst_product",
        lambda c: (fake_obs, JWSTProductValidation(
            valid=True, product_path="x.fits", n_points=100)),
    )

    r = p.process_product(_contract(product_path=str(tmp_path / "x.fits")))
    assert r.success is True
    assert r.noise_ppm == 42.0
    assert r.transit_confirmed is False
