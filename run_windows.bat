@echo off
setlocal

cd /d "%~dp0"

py -m pip install -r requirements.txt
if errorlevel 1 goto failed

py app.py
exit /b 0

:failed
echo.
echo Could not install or run the app. Make sure Python is installed from https://www.python.org/downloads/windows/
pause
exit /b 1
