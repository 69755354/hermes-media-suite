@echo off
REM ==========================================================================
REM  Import the licence we sent you (license.json).  Double-click me.
REM  Put license.json in the "license" folder next to this file first
REM  (or drag license.json onto me).
REM ==========================================================================
setlocal
set "HERE=%~dp0"
if not "%~1"=="" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\import-license.ps1" -Program "%HERE%." -Src "%~1"
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\import-license.ps1" -Program "%HERE%."
)
echo.
pause
exit /b %ERRORLEVEL%
