#!/bin/sh
# macOS/Linux. Wymaga Pythona z Tk (brew install python-tk@3.15).
# Przyklad: ./run.sh  |  ./run.sh macos/ruch/ruch_mac.py  |  ./run.sh macos/kamera_mac.py --test
cd "$(dirname "$0")"
PY=${PY:-python3}
SCRIPT=${1:-kamera.py}
[ $# -gt 0 ] && shift
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python "$SCRIPT" "$@"
