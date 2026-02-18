@echo off
setlocal enabledelayedexpansion

REM ============================================================
REM SAVH Print App - Instalación de servicios con NSSM (Windows)
REM ============================================================
REM Requisitos:
REM   - NSSM instalado (https://nssm.cc/) o nssm.exe disponible
REM   - Poetry instalado y funcionando
REM   - Este .bat se ejecuta con permisos para instalar servicios
REM
REM Importante:
REM   - REPO_DIR debe ser la carpeta del proyecto (donde esta .env)
REM   - Si NSSM no encuentra "poetry" por PATH, setea POETRY_EXE con ruta completa.
REM

REM ====== EDITA ESTAS VARIABLES ======
set "NSSM_EXE=nssm.exe"
set "REPO_DIR=C:\path\to\savh_print_app"
set "POETRY_EXE=poetry"

set "HOST=127.0.0.1"
set "PORT=8000"

set "LOG_DIR=%REPO_DIR%\data\logs"
set "ROTATE_BYTES=10485760"

set "SVC_API=savh-api"
set "SVC_GEN=savh-worker-generate"
set "SVC_PRINT=savh-worker-print"
REM ==================================

if not exist "%REPO_DIR%" (
  echo ERROR: REPO_DIR no existe: %REPO_DIR%
  exit /b 1
)

if not exist "%LOG_DIR%" (
  mkdir "%LOG_DIR%" >nul 2>&1
)

echo.
echo Instalando/actualizando servicios NSSM...
echo   REPO_DIR=%REPO_DIR%
echo   POETRY_EXE=%POETRY_EXE%
echo   LOG_DIR=%LOG_DIR%
echo.

REM ----------------------
REM API service
REM ----------------------
%NSSM_EXE% stop "%SVC_API%" >nul 2>&1
%NSSM_EXE% remove "%SVC_API%" confirm >nul 2>&1

%NSSM_EXE% install "%SVC_API%" "%POETRY_EXE%" run uvicorn print_server.app.main:app --host %HOST% --port %PORT%
%NSSM_EXE% set "%SVC_API%" AppDirectory "%REPO_DIR%"
%NSSM_EXE% set "%SVC_API%" DisplayName "SAVH Print App - API"
%NSSM_EXE% set "%SVC_API%" Description "FastAPI (SAVH Print App)"
%NSSM_EXE% set "%SVC_API%" Start SERVICE_AUTO_START
%NSSM_EXE% set "%SVC_API%" AppStdout "%LOG_DIR%\service_api.out.log"
%NSSM_EXE% set "%SVC_API%" AppStderr "%LOG_DIR%\service_api.err.log"
%NSSM_EXE% set "%SVC_API%" AppRotateFiles 1
%NSSM_EXE% set "%SVC_API%" AppRotateBytes %ROTATE_BYTES%

REM ----------------------
REM Generate worker service
REM ----------------------
%NSSM_EXE% stop "%SVC_GEN%" >nul 2>&1
%NSSM_EXE% remove "%SVC_GEN%" confirm >nul 2>&1

%NSSM_EXE% install "%SVC_GEN%" "%POETRY_EXE%" run python -m create_prints_server.worker.generate_worker
%NSSM_EXE% set "%SVC_GEN%" AppDirectory "%REPO_DIR%"
%NSSM_EXE% set "%SVC_GEN%" DisplayName "SAVH Print App - Worker (Generate)"
%NSSM_EXE% set "%SVC_GEN%" Description "Worker de generacion de PDFs (Google Sheets -> PDFs)"
%NSSM_EXE% set "%SVC_GEN%" Start SERVICE_AUTO_START
%NSSM_EXE% set "%SVC_GEN%" AppStdout "%LOG_DIR%\service_generate.out.log"
%NSSM_EXE% set "%SVC_GEN%" AppStderr "%LOG_DIR%\service_generate.err.log"
%NSSM_EXE% set "%SVC_GEN%" AppRotateFiles 1
%NSSM_EXE% set "%SVC_GEN%" AppRotateBytes %ROTATE_BYTES%

REM ----------------------
REM Print worker service
REM ----------------------
%NSSM_EXE% stop "%SVC_PRINT%" >nul 2>&1
%NSSM_EXE% remove "%SVC_PRINT%" confirm >nul 2>&1

%NSSM_EXE% install "%SVC_PRINT%" "%POETRY_EXE%" run python -m print_server.worker.print_worker
%NSSM_EXE% set "%SVC_PRINT%" AppDirectory "%REPO_DIR%"
%NSSM_EXE% set "%SVC_PRINT%" DisplayName "SAVH Print App - Worker (Print)"
%NSSM_EXE% set "%SVC_PRINT%" Description "Worker de impresion (SumatraPDF -> impresora)"
%NSSM_EXE% set "%SVC_PRINT%" Start SERVICE_AUTO_START
%NSSM_EXE% set "%SVC_PRINT%" AppStdout "%LOG_DIR%\service_print.out.log"
%NSSM_EXE% set "%SVC_PRINT%" AppStderr "%LOG_DIR%\service_print.err.log"
%NSSM_EXE% set "%SVC_PRINT%" AppRotateFiles 1
%NSSM_EXE% set "%SVC_PRINT%" AppRotateBytes %ROTATE_BYTES%

echo.
echo Iniciando servicios...
%NSSM_EXE% start "%SVC_API%"
%NSSM_EXE% start "%SVC_GEN%"
%NSSM_EXE% start "%SVC_PRINT%"

echo.
echo OK: servicios instalados e iniciados.
echo Logs:
echo   %LOG_DIR%\service_api.out.log
echo   %LOG_DIR%\service_generate.out.log
echo   %LOG_DIR%\service_print.out.log
echo.
echo Para detener:
echo   %NSSM_EXE% stop "%SVC_API%"
echo   %NSSM_EXE% stop "%SVC_GEN%"
echo   %NSSM_EXE% stop "%SVC_PRINT%"
echo.
echo Para borrar:
echo   %NSSM_EXE% remove "%SVC_API%" confirm
echo   %NSSM_EXE% remove "%SVC_GEN%" confirm
echo   %NSSM_EXE% remove "%SVC_PRINT%" confirm

endlocal

