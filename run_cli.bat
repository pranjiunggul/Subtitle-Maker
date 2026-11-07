@echo off
title Subtitle Maker — CLI Runner
cd /d "%~dp0"
call venv\Scripts\activate.bat
python app.py --cli %*
