@echo off
REM Buduje dist\BT_Telefon.exe (do oddania razem ze sprawozdaniem).
cd /d "%~dp0"
python -m pip install -q pyinstaller
python -m PyInstaller --onefile --windowed --name BT_Telefon bt_telefon_windows.py
pause
