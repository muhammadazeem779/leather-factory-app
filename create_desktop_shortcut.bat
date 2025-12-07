@echo off

REM Get current folder (where this BAT file lives)
set APPDIR=%~dp0

REM Desktop path
set DESKTOP=%USERPROFILE%\Desktop

REM Shortcut name
set SHORTCUT_NAME=Leather Factory App.lnk

REM Create VBS file temporarily
set VBSFILE=%TEMP%\create_shortcut.vbs

echo Set oWS = CreateObject("WScript.Shell") > "%VBSFILE%"
echo sLinkFile = "%DESKTOP%\%SHORTCUT_NAME%" >> "%VBSFILE%"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%VBSFILE%"
echo oLink.TargetPath = "%APPDIR%run_leather_app.bat" >> "%VBSFILE%"
echo oLink.WorkingDirectory = "%APPDIR%" >> "%VBSFILE%"
echo oLink.WindowStyle = 1 >> "%VBSFILE%"
echo oLink.Description = "Run Leather Factory Application" >> "%VBSFILE%"
echo oLink.Save >> "%VBSFILE%"

REM Run VBS to create shortcut
cscript //nologo "%VBSFILE%"

REM Cleanup
del "%VBSFILE%"

echo.
echo ✅ Desktop shortcut created successfully!
echo.
pause
