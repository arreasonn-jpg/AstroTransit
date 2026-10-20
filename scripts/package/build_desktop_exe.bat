@echo off
REM AstroTransit masaüstü uygulaması Windows .exe paketi oluşturur.
REM Önkogullar: Python 3.11+ ve `python -m pip install -e ".[gui]"` tamamlanmış olsun.
setlocal
cd /d "%~dp0\..\.."

echo [1/3] PyInstaller kurulum kontrolu...
python -m pip show pyinstaller >nul 2>&1 || python -m pip install pyinstaller
if errorlevel 1 goto :fail

echo [2/3] Paketleme (onedir)...
python -m PyInstaller packaging\astrotransit-desktop.spec --noconfirm
if errorlevel 1 goto :fail

echo [3/3] Smoke dogrulamasi...
set QT_QPA_PLATFORM=offscreen
dist\AstroTransitDesktop\AstroTransitDesktop.exe --smoke
if errorlevel 1 goto :fail

echo.
echo BASARILI: dist\AstroTransitDesktop\AstroTransitDesktop.exe
exit /b 0

:fail
echo HATA: paketleme basarisiz.
exit /b 1
