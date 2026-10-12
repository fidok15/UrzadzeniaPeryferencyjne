#!/bin/sh
# Buduje dist/GPS_NMEA.app
cd "$(dirname "$0")"
PY=${PY:-python3}
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt pyinstaller
.venv/bin/python -m PyInstaller --windowed --name GPS_NMEA gps_app.py
echo "Gotowe: dist/GPS_NMEA.app"
