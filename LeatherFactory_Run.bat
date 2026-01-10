@echo off
setlocal
title Leather Factory - One Click Run

set "APPDIR=D:\leather-factory-app"

cd /d "%APPDIR%" || (
  echo Folder not found: %APPDIR%
  pause
  exit /b 1
)

python --version >nul 2>&1 || (
  echo Python not found.
  echo Install Python 3 from python.org (check "Add python to PATH") then run this again.
  pause
  exit /b 1
)

python -m ensurepip --upgrade >nul 2>&1

python -c "import flask" >nul 2>&1
if errorlevel 1 (
  echo Flask missing. Installing now...
  python -m pip install --upgrade pip
  python -m pip install flask
)

echo Starting app...
start "" python app.py

timeout /t 3 >nul
start "" http://localhost:5000

endlocal
exit
