@echo off
REM 1.2.32: target for the Import License shortcut.
REM A .lnk to powershell.exe cannot receive Explorer's dragged file through a
REM %1 placeholder, so the shortcut targets this small cmd shim instead.  cmd.exe
REM receives the dropped path as %1 and forwards it to import-license.ps1.
setlocal
for %%I in ("%~dp0..") do set "PROGRAM=%%~fI"
if "%~1"=="" (
  powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0import-license.ps1" -Program "%PROGRAM%"
) else (
  powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0import-license.ps1" -Program "%PROGRAM%" -Src "%~1"
)
set "RC=%ERRORLEVEL%"
exit /b %RC%
