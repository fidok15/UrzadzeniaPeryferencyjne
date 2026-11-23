@echo off
REM Buduje dist\kamera.exe (Windows, zad. 1).
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -q -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name kamera kamera.py
pause
