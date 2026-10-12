#!/bin/sh
# Wymaga Pythona z Tk 8.6+ (python.org albo: brew install python-tk@3.14).
cd "$(dirname "$0")"
PY=${PY:-python3}
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python gps_app.py
