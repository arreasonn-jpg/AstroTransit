"""
MASTClient birim testleri.

Strateji
--------
astroquery Observations ve Catalogs module-level monkeypatch ile
mock'lanir. Gercek ag sorgusu yapilmaz.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from astrotransit.data import mast_client as m_module
from astrotransit.data.mast_client import (
    MASTClient,
    MASTConnectionError,
    MASTQueryError,
)

# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_obs() -> MagicMock:
    return MagicMock(name="Observations")


@pytest.fixture
def mock_cat() -> MagicMock:
    return MagicMock(name="Catalogs")


@pytest.fixture
def patched_module(mock_obs, mock_cat, monkeypatch):
    monkeypatch.setattr(m_module, "Observations", mock_obs)
    monkeypatch.setattr(m_module, "Catalogs", mock_cat)
    return mock_obs, mock_cat


# ─────────────────────────────────────────────────────────────
# _require_dependency
# ─────────────────────────────────────────────────────────────

def test_require_dependency_ok(patched_module) -> None:
    MASTClient._require_dependency()  # hata yok


def test_require_dependency_raises_when_missing(monkeypatch) -> None:
    monkeypatch.setattr(m_module, "Observations", None)
    monkeypatch.setattr(m_module, "Catalogs", None)
    with pytest.raises(MASTConnectionError, match="astroquery"):
        MASTClient._require_dependency()


def test_require_dependency_raises_when_only_obs_missing(monkeypatch, mock_cat) -> None:
    monkeypatch.setattr(m_module, "Observations", None)
    monkeypatch.setattr(m_module, "Catalogs", mock_cat)
    with pytest.raises(MASTConnectionError):
        MASTClient._require_dependency()


# ─────────────────────────────────────────────────────────────
# __init__
# ─────────────────────────────────────────────────────────────

def test_init_anonymous(patched_module) -> None:
    c = MASTClient()
    assert c.is_authenticated is False


def test_init_with_token_success(patched_module) -> None:
    mock_obs, _ = patched_module
    c = MASTClient(api_token="abc123")
    assert c.is_authenticated is True
    mock_obs.login.assert_called_once_with(token="abc123")


def test_init_with_token_failure_falls_back(patched_module) -> None:
    mock_obs, _ = patched_module
    mock_obs.login.side_effect = RuntimeError("auth fail")
    c = MASTClient(api_token="bad")
    assert c.is_authenticated is False


# ─────────────────────────────────────────────────────────────
# query_observations
# ─────────────────────────────────────────────────────────────

def test_query_observations_by_target_name(patched_module) -> None:
    mock_obs, _ = patched_module
    fake = MagicMock()
    fake.__len__ = lambda self: 3
    mock_obs.query_object.return_value = fake
    # gercek Table yerine MagicMock kullaniyoruz

    c = MASTClient()
    _result = c.query_observations(target_name="TIC 123")
    mock_obs.query_object.assert_called_once_with("TIC 123", radius="0.02 deg")


def test_query_observations_by_coordinates(patched_module) -> None:
    mock_obs, _ = patched_module
    fake = MagicMock()
    fake.__len__ = lambda self: 5
    mock_obs.query_criteria.return_value = fake

    c = MASTClient()
    c.query_observations(coordinates="350.0 -20.0", radius="0.01 deg")
    mock_obs.query_criteria.assert_called_once()
    kwargs = mock_obs.query_criteria.call_args.kwargs
    assert kwargs["coordinates"] == "350.0 -20.0"
    assert kwargs["radius"] == "0.01 deg"


def test_query_observations_with_filters(patched_module) -> None:
    mock_obs, _ = patched_module
    fake = MagicMock()
    fake.__len__ = lambda self: 2
    mock_obs.query_criteria.return_value = fake

    c = MASTClient()
    c.query_observations(
        coordinates="350.0 -20.0",
        filters={"t_min": 100.0, "t_max": 200.0},
    )
    kwargs = mock_obs.query_criteria.call_args.kwargs
    assert kwargs["t_min"] == 100.0
    assert kwargs["t_max"] == 200.0


def test_query_observations_raises_query_error(patched_module) -> None:
    mock_obs, _ = patched_module
    mock_obs.query_object.side_effect = RuntimeError("network")
    c = MASTClient()
    with pytest.raises(MASTQueryError, match="MAST sorgusu"):
        c.query_observations(target_name="TIC 1")


# ─────────────────────────────────────────────────────────────
# get_product_list
# ─────────────────────────────────────────────────────────────

def test_get_product_list_empty_table(patched_module) -> None:
    c = MASTClient()
    empty = MagicMock()
    empty.__len__ = lambda self: 0
    result = c.get_product_list(empty)
    # Bos Table donmeli
    from astropy.table import Table
    assert isinstance(result, Table)


def test_get_product_list_non_empty(patched_module) -> None:
    mock_obs, _ = patched_module
    fake_result = MagicMock()
    fake_result.__len__ = lambda self: 2
    mock_obs.get_product_list.return_value = fake_result

    c = MASTClient()
    obs = MagicMock()
    obs.__len__ = lambda self: 1
    result = c.get_product_list(obs)
    assert result is fake_result


def test_get_product_list_raises_query_error(patched_module) -> None:
    mock_obs, _ = patched_module
    mock_obs.get_product_list.side_effect = RuntimeError("network")

    c = MASTClient()
    obs = MagicMock()
    obs.__len__ = lambda self: 1
    with pytest.raises(MASTQueryError, match="Ürün listesi"):
        c.get_product_list(obs)


# ─────────────────────────────────────────────────────────────
# query_tic_catalog
# ─────────────────────────────────────────────────────────────

def test_query_tic_by_id(patched_module, monkeypatch) -> None:
    _, mock_cat = patched_module
    fake = MagicMock()
    fake.__len__ = lambda self: 1
    mock_cat.query_object.return_value = fake

    # time.sleep'i mockla
    monkeypatch.setattr("time.sleep", lambda s: None)

    c = MASTClient()
    result = c.query_tic_catalog(tic_id=123456789)
    assert result is fake
    mock_cat.query_object.assert_called_once_with(
        "TIC 123456789", catalog="TIC", radius="0.02 deg",
    )


def test_query_tic_by_coordinates(patched_module, monkeypatch) -> None:
    _, mock_cat = patched_module
    fake = MagicMock()
    fake.__len__ = lambda self: 1
    mock_cat.query_region.return_value = fake
    monkeypatch.setattr("time.sleep", lambda s: None)

    c = MASTClient()
    result = c.query_tic_catalog(coordinates="350 -20")
    assert result is fake
    mock_cat.query_region.assert_called_once()


def test_query_tic_no_params_raises(patched_module, monkeypatch) -> None:
    monkeypatch.setattr("time.sleep", lambda s: None)
    c = MASTClient()
    with pytest.raises(MASTQueryError):
        c.query_tic_catalog()


def test_query_tic_retries_three_times(patched_module, monkeypatch) -> None:
    _, mock_cat = patched_module
    mock_cat.query_object.side_effect = RuntimeError("network")

    sleeps: list[float] = []
    monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))

    c = MASTClient()
    with pytest.raises(MASTQueryError):
        c.query_tic_catalog(tic_id=1)

    assert mock_cat.query_object.call_count == 3
    # Sleep sadece 2 kez (son denemede yok): 1, 2
    assert sleeps == [1, 2]


def test_query_tic_succeeds_after_retry(patched_module, monkeypatch) -> None:
    _, mock_cat = patched_module
    fake = MagicMock()
    fake.__len__ = lambda self: 1
    mock_cat.query_object.side_effect = [RuntimeError("transient"), fake]
    monkeypatch.setattr("time.sleep", lambda s: None)

    c = MASTClient()
    result = c.query_tic_catalog(tic_id=1)
    assert result is fake
    assert mock_cat.query_object.call_count == 2
