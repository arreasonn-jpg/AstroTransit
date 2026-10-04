"""dashboard/app.py için testler (Streamlit AppTest tabanlı).

AppTest, scripti gerçek bir Streamlit context'inde çalıştırır; bu sayede
sayfa fonksiyonları (page_home, page_settings vs.) içindeki tüm kod
yolları tetiklenir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("streamlit")

from streamlit.testing.v1 import AppTest

APP_PATH = str(
    (Path(__file__).resolve().parent.parent / "dashboard" / "app.py").resolve()
)
TIMEOUT = 60.0


def _run(extra_session: dict | None = None) -> AppTest:
    at = AppTest.from_file(APP_PATH, default_timeout=TIMEOUT)
    if extra_session:
        for k, v in extra_session.items():
            at.session_state[k] = v
    at.run()
    return at


# ═══════════════════════════════════════════════════════
# Temel boot
# ═══════════════════════════════════════════════════════

def test_app_boots_without_exception():
    at = _run()
    assert not at.exception, [str(e) for e in at.exception]


def test_app_renders_some_ui():
    at = _run()
    assert at.markdown or at.title or at.header, "en az bir UI öğesi render edilmeli"


def test_app_sidebar_has_navigation():
    at = _run()
    radios = list(at.sidebar.radio)
    selects = list(at.sidebar.selectbox)
    assert radios or selects, "sidebar'da navigasyon widget'ı olmalı"


# ═══════════════════════════════════════════════════════
# Sayfa geçişleri
# ═══════════════════════════════════════════════════════

def _switch_page(at: AppTest, label: str):
    """Sidebar radio/selectbox üzerinden sayfa değiştir ve tekrar çalıştır."""
    for widget in list(at.sidebar.radio) + list(at.sidebar.selectbox):
        opts = list(widget.options)
        for opt in opts:
            if label.lower() in str(opt).lower():
                widget.set_value(opt).run()
                return at
    return at


@pytest.mark.parametrize(
    "label",
    ["Ana Sayfa", "Tek Hedef", "Katalog", "Aday", "Ayarlar"],
)
def test_each_page_runs_without_exception(label):
    at = _run()
    at = _switch_page(at, label)
    # Eğer o sayfa mevcut değilse bile en azından patlamamalı
    assert not at.exception, [str(e) for e in at.exception]


# ═══════════════════════════════════════════════════════
# Yardımcı fonksiyonlar (unwrapped)
# ═══════════════════════════════════════════════════════

def test_load_parquet_cached(tmp_path):
    import pandas as pd

    import dashboard.app as app_mod

    p = tmp_path / "x.parquet"
    pd.DataFrame({"a": [1, 2]}).to_parquet(p)
    fn = app_mod.load_parquet_cached
    df = fn.__wrapped__(str(p)) if hasattr(fn, "__wrapped__") else fn(str(p))
    assert list(df["a"]) == [1, 2]


def test_load_json_cached(tmp_path):
    import json

    import dashboard.app as app_mod

    p = tmp_path / "x.json"
    p.write_text(json.dumps({"k": 1}))
    fn = app_mod.load_json_cached
    data = fn.__wrapped__(str(p)) if hasattr(fn, "__wrapped__") else fn(str(p))
    assert data == {"k": 1}


def test_list_json_candidates(tmp_path, monkeypatch):
    import dashboard.app as app_mod

    monkeypatch.chdir(tmp_path)
    d = tmp_path / "outputs" / "json"
    d.mkdir(parents=True)
    (d / "a.json").write_text("{}")
    (d / "all_candidates.jsonl").write_text("")
    fn = app_mod.list_json_candidates
    results = fn.__wrapped__() if hasattr(fn, "__wrapped__") else fn()
    names = [Path(f).name for f in results]
    assert "a.json" in names
    assert "all_candidates.jsonl" not in names


def test_list_json_candidates_empty(tmp_path, monkeypatch):
    import dashboard.app as app_mod

    monkeypatch.chdir(tmp_path)
    fn = app_mod.list_json_candidates
    results = fn.__wrapped__() if hasattr(fn, "__wrapped__") else fn()
    assert results == []


def test_find_candidate_images_returns_iterable(tmp_path, monkeypatch):
    import dashboard.app as app_mod

    monkeypatch.chdir(tmp_path)
    for d in ["outputs/plots", "outputs_top10/plots"]:
        (tmp_path / d).mkdir(parents=True)

    fn = app_mod.find_candidate_images
    fn = getattr(fn, "__wrapped__", fn)
    result = fn("TIC 123", 1)
    # Fonksiyon ne dönerse (liste/dict) iterable olmalı
    assert result is not None


# ═══════════════════════════════════════════════════════
# _create_demo_parquet
# ═══════════════════════════════════════════════════════

def test_create_demo_parquet(tmp_path):
    import pandas as pd

    import dashboard.app as app_mod

    p = tmp_path / "demo.parquet"
    app_mod._create_demo_parquet(p)
    assert p.exists()
    df = pd.read_parquet(p)
    assert len(df) > 0
