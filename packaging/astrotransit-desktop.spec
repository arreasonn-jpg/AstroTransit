# -*- mode: python ; coding: utf-8 -*-
r"""AstroTransit Masaüstü (PySide6) PyInstaller spec dosyası.

Kullanım:
    # Windows  → dist\AstroTransitDesktop\AstroTransitDesktop.exe
    pyinstaller packaging\\astrotransit-desktop.spec --noconfirm

    # Linux/WSLg → dist/AstroTransitDesktop/AstroTransitDesktop
    pyinstaller packaging/astrotransit-desktop.spec --noconfirm

Notlar:
- agır opsiyonel paketler (pymc, arviz, exoplanet, celerite2, streamlit,
  plotly) bilinçli olarak dislanir; MCMC/JWST extras CLI uzerinden
  gelistirme kurulumunda kullanilir, exe icinde gerekmez.
- onedir düzeni secilir: astropy/astroquery veri dosyalari tekil exe
  icinde şişirir ve cikti klasörüde (outputs/) kalıcı konumu gider.
"""
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH: spec dosyasının bulunduğu dizin (repo kökü = onun parent'ı değil;
# spec packaging/ altında olduğu için repo kökü bir üst seviyedir).
ROOT = os.path.dirname(SPECPATH)

datas = []
# Konfigürasyon: exe/bundle kökünde configs/ olacak; load_settings o dizinde
# default.toml'u arar (astrotransit/settings.py → project_root/configs).
datas += [(os.path.join(ROOT, "configs"), "configs")]
datas += collect_data_files("astroquery")

hiddenimports = []
hiddenimports += collect_submodules("astrotransit")
hiddenimports += collect_submodules("desktop")
hiddenimports += collect_submodules("cli")

excludes = [
    "pymc", "arviz", "exoplanet", "exoplanet_core", "celerite2",
    "streamlit", "plotly", "altair",
    "IPython", "jupyterlab", "pytest", "mypy", "ruff",
    "tkinter", "PyQt5", "PyQt6",
    # torch, astrotransit calisma zincirinde kullanilmaz (dogrulandi: tum
    # pipeline modulleri torch'suz import edilir); sklearn array-API uyumluluk
    # katmanindan tasinarak exe'yi ~1 GB sistirmisti.
    "torch", "torchvision", "torchaudio",
]

a = Analysis(
    [os.path.join(SPECPATH, "desktop_entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="AstroTransitDesktop",
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="AstroTransitDesktop",
)
