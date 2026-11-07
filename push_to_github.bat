@echo off
title Push Subtitle Maker ke GitHub
color 0b

echo ======================================================================
echo             🚀 PUSH SUBTITLE MAKER KE GITHUB
echo ======================================================================
echo.

cd /d "%~dp0"
set "PATH=%PATH%;C:\Users\user\AppData\Local\Programs\Git\cmd;C:\Users\user\AppData\Local\Programs\gh"

:: Cek apakah git remote origin sudah ada
git remote get-url origin >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [*] Remote origin sudah terkonfigurasi.
    git remote -v
    echo.
    echo [*] Melakukan push ke origin main...
    git push -u origin main
    goto FINISH
)

echo Pilih metode untuk mengunggah ke GitHub:
echo [1] Otomatis via GitHub CLI (Login web langsung buat repo di akun Anda)
echo [2] Masukkan URL Repositori GitHub manual (misal: https://github.com/username/repo.git)
echo.
set /p CHOICE="Pilihan Anda (1 atau 2): "

if "%CHOICE%"=="2" goto MANUAL_URL
if "%CHOICE%"=="1" goto GH_CLI

:GH_CLI
echo.
echo [*] Memeriksa status login GitHub...
gh auth status >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [!] Anda belum login ke GitHub.
    echo [*] Membuka login web GitHub (pilih protocol HTTPS)...
    echo.
    gh auth login --web -p https
)

echo.
echo Pilih visibilitas repositori di GitHub:
echo [1] Public (Bisa dilihat siapa saja)
echo [2] Private (Hanya Anda yang bisa lihat)
set /p VIS="Pilihan visibilitas (1 atau 2, default 1): "

set "VIS_FLAG=--public"
if "%VIS%"=="2" set "VIS_FLAG=--private"

echo.
echo [*] Membuat repositori 'Subtitle-Maker' di akun GitHub Anda dan melakukan push...
gh repo create Subtitle-Maker %VIS_FLAG% --source=. --remote=origin --push

goto FINISH

:MANUAL_URL
echo.
set /p REPO_URL="Masukkan URL repositori GitHub Anda: "
if "%REPO_URL%"=="" (
    echo [!] URL tidak boleh kosong.
    goto MANUAL_URL
)

git remote add origin %REPO_URL%
echo [*] Melakukan push ke %REPO_URL%...
git push -u origin main

:FINISH
echo.
if %ERRORLEVEL% equ 0 (
    echo ======================================================================
    echo  ✅ BERHASIL! Proyek Subtitle Maker sudah ada di GitHub Anda!
    echo ======================================================================
) else (
    echo ======================================================================
    echo  [!] Terjadi kendala saat push. Silakan periksa pesan di atas.
    echo ======================================================================
)
echo.
pause
