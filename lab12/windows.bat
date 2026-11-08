@echo off
REM Windows ^<-^> Windows (wysylanie i odbior). Python 3.9+ z python.org, bez dodatkowych pakietow.
cd /d "%~dp0"
python bt_windows.py %*
pause
