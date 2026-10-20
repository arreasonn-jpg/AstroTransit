#!/usr/bin/env bash
# AstroTransit masaüstü uygulaması Linux/WSLg paketi (onedir).
# Kullanım: bash scripts/package/build_desktop_exe.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

PY="${PYTHON:-python3}"
if ! "$PY" -c "import PyInstaller" 2>/dev/null; then
  echo "[1/3] PyInstaller kuruluyor..."
  "$PY" -m pip install pyinstaller
fi

echo "[2/3] Paketleme (onedir)..."
"$PY" -m PyInstaller packaging/astrotransit-desktop.spec --noconfirm

echo "[3/3] Smoke dogrulamasi..."
QT_QPA_PLATFORM=offscreen dist/AstroTransitDesktop/AstroTransitDesktop --smoke

echo "BASARILI: dist/AstroTransitDesktop/AstroTransitDesktop"
