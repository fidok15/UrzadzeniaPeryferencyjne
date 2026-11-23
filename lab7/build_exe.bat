@echo off
REM Buduje dist\kamera.exe (zad. 1) oraz dist\ruch.exe, www.exe, anaglif.exe, hdr.exe (zad. 2).
cd /d "%~dp0"
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -q -r requirements.txt pyinstaller
.venv\Scripts\pyinstaller --noconfirm --onefile --windowed --name kamera kamera.py
for %%v in (ruch www anaglif hdr) do .venv\Scripts\pyinstaller --noconfirm --onefile --windowed --paths . --name %%v zad2_%%v\%%v.py
pause
