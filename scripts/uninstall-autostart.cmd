@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-autostart.ps1" %*
exit /b %ERRORLEVEL%
