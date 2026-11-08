#!/bin/sh
# macOS -> telefon z Androidem. Wymaga Pythona z Tk: brew install python-tk@3.15
cd "$(dirname "$0")"
PY=${PY:-python3}
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python bt_telefon.py "$@"
