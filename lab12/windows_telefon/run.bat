@echo off
REM Windows -> telefon z Androidem. Wymaga Pythona 3.9+ z python.org (ma tkinter), bez dodatkowych pakietow.
cd /d "%~dp0"
python bt_telefon_windows.py %*
pause
