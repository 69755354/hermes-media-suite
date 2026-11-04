@echo off
REM ==========================================================================
REM  Show this machine's code (ЛњЦїТы).  Double-click me.
REM  Also saved to %LOCALAPPDATA%\HuolongAgent\publish-worker\logs\ЛњЦїТы.txt
REM ==========================================================================
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\show-machine-code.ps1" -Program "%HERE%."
echo.
pause
exit /b %ERRORLEVEL%
