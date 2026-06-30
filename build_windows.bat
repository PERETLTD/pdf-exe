@echo off
setlocal

cd /d "%~dp0"

echo Installing build tools on this builder computer...
py -m pip install --upgrade pip
if errorlevel 1 goto failed

py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto failed

echo.
echo Building standalone PDF Number Editor.exe...
py -m PyInstaller ^
  --clean ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --hidden-import email.parser ^
  --hidden-import email.policy ^
  --hidden-import email.message ^
  --hidden-import email.mime.multipart ^
  --hidden-import email.mime.text ^
  --name "PDF Number Editor" ^
  app.py
if errorlevel 1 goto failed

echo.
echo Done.
echo.
echo Send this file to users:
echo %cd%\dist\PDF Number Editor.exe
echo.
echo Users do NOT need Python installed. They only double-click the EXE.
pause
exit /b 0

:failed
echo.
echo Build failed. Check the error above.
pause
exit /b 1
