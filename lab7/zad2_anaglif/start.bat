@echo off
REM Windows: Python 3.9+ z python.org. Pierwsze uruchomienie instaluje OpenCV do ..\.venv
cd /d "%~dp0.."
if not exist .venv python -m venv .venv
.venv\Scripts\pip install -q -r requirements.txt
.venv\Scripts\python zad2_anaglif\anaglif.py %*
pause
