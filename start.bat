@echo off
title Subtitle Maker — Lightweight Standalone (4GB RAM Ready)
color 0b

echo ======================================================================
echo             🧠 SUBTITLE MAKER — LIGHTWEIGHT STANDALONE
echo             Hemat RAM (Laptop 4GB) - Cepat & Mandiri
echo ======================================================================
echo.

cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo [!] Virtual environment belum terdeteksi. Membuat venv...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)

echo [*] Menjalankan server Subtitle Maker...
echo [*] Membuka browser di http://localhost:5050
echo.
python app.py --port 5050

pause
