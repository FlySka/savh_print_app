@echo off
setlocal

REM Wrapper para usar scripts\windows\savh.ps1 desde la ruta "scripts".

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows\savh.ps1" %*

endlocal
