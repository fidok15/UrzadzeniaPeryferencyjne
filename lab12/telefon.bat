@echo off
REM Windows -> telefon z Androidem. Python 3.9+ z python.org, bez dodatkowych pakietow.
cd /d "%~dp0"
python bt_telefon.py %*
pause
