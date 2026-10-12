@echo off
rem Buduje dist\GPS_NMEA.exe (do oddania ze sprawozdaniem)
cd /d %~dp0
python -m pip install -q -r requirements.txt pyinstaller
python -m PyInstaller --onefile --windowed --name GPS_NMEA gps_app.py
echo Gotowe: dist\GPS_NMEA.exe
pause
