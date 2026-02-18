@echo off
setlocal

REM Wrapper para ejecutar savh.ps1 sin pelear con ExecutionPolicy.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0savh.ps1" %*

endlocal

