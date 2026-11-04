@echo off
setlocal
set "HERE=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\selftest.ps1"
pause
exit /b %ERRORLEVEL%
