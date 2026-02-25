@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM SAVH Print App - Instalación de servicios con NSSM (Windows)
REM ============================================================
REM Requisitos (recomendado):
REM   - NSSM instalado y accesible como "nssm.exe" (PATH) o seteando NSSM_EXE
REM   - Dependencias instaladas (Poetry + venv). Ideal: venv in-project en .venv\
REM   - Ejecutar este .bat como Administrador (instalar/gestionar servicios)
REM
REM Importante:
REM   - AppDirectory debe ser la carpeta del proyecto (donde está .env) para que python-dotenv/pydantic lo carguen.
REM   - Para que los servicios NO dependan de que "poetry" esté en el PATH del usuario del servicio,
REM     este script usa .venv\Scripts\python.exe si existe.
REM
REM Cómo instalar NSSM (manual):
REM   1) Descarga: https://nssm.cc/download
REM   2) Extrae y copia el nssm.exe (carpeta win64/) a, por ejemplo: C:\Tools\nssm\nssm.exe
REM   3) Agrega C:\Tools\nssm al PATH (o setea NSSM_EXE=C:\Tools\nssm\nssm.exe antes de correr este .bat)
REM

REM =============================
REM Overrides opcionales (env)
REM =============================
REM   set NSSM_EXE=C:\Tools\nssm\nssm.exe
REM   set POETRY_EXE=C:\Users\...\poetry.exe
REM   set HOST=127.0.0.1
REM   set PORT=8000
REM   set ROTATE_BYTES=10485760
REM   set LOG_DIR=C:\path\to\savh_print_app\data\logs
REM =============================

set "CMD=%~1"
if "%CMD%"=="" set "CMD=install"
if /i not "%CMD%"=="install" if /i not "%CMD%"=="uninstall" if /i not "%CMD%"=="remove" goto :usage

REM Repo root = parent de \scripts (este archivo vive en scripts\)
for %%I in ("%~dp0.") do set "SCRIPTS_DIR=%%~fI"
for %%I in ("%SCRIPTS_DIR%\..") do set "REPO_DIR=%%~fI"

if not defined HOST set "HOST=0.0.0.0"
if not defined PORT set "PORT=8000"
if not defined ROTATE_BYTES set "ROTATE_BYTES=10485760"

if not defined LOG_DIR set "LOG_DIR=%REPO_DIR%\data\logs"

set "SVC_API=savh-api"
set "SVC_GEN=savh-worker-generate"
set "SVC_PRINT=savh-worker-print"

REM Intenta resolver NSSM_EXE si no está seteado.
if defined NSSM_EXE (
  REM Permite que NSSM_EXE venga con comillas (ej: "C:\Program Files\...\nssm.exe").
  set "NSSM_EXE=%NSSM_EXE:"=%"
  REM Si te pasan ruta completa, valida que exista.
  if exist "%NSSM_EXE%" goto :nssm_check
)

REM Si no viene ruta, intenta resolver por PATH.
for %%C in (nssm.exe nssm) do (
  for /f "usebackq delims=" %%I in (`where %%C 2^>nul`) do (
    set "NSSM_EXE=%%I"
    goto :nssm_check
  )
)

REM Fallback a rutas comunes (si no está en PATH).
if not defined NSSM_EXE (
  if exist "%ProgramFiles%\nssm\win64\nssm.exe" set "NSSM_EXE=%ProgramFiles%\nssm\win64\nssm.exe"
  if not defined NSSM_EXE if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\nssm\win64\nssm.exe" set "NSSM_EXE=%ProgramFiles(x86)%\nssm\win64\nssm.exe"
)

if not defined NSSM_EXE set "NSSM_EXE=nssm.exe"
:nssm_check

if not exist "%REPO_DIR%" (
  echo ERROR: REPO_DIR no existe: "%REPO_DIR%"
  exit /b 1
)

REM Verifica admin (necesario para instalar servicios).
net session >nul 2>&1
if not "%ERRORLEVEL%"=="0" (
  echo ERROR: ejecuta este .bat como Administrador.
  echo Tip: click derecho ^> "Run as administrator"
  exit /b 1
)

REM Verifica NSSM (existencia). Nota: NSSM 2.24 puede devolver exit code != 0 en "--help".
if not exist "%NSSM_EXE%" (
  echo ERROR: no se encontró NSSM. Probado: "%NSSM_EXE%"
  echo - O pon nssm.exe en el PATH
  echo - O ejecuta: set NSSM_EXE=C:\ruta\completa\a\nssm.exe
  exit /b 1
)

REM Runtime preferido: .venv\Scripts\python.exe (no depende de Poetry en el PATH del servicio).
set "PY_EXE=%REPO_DIR%\.venv\Scripts\python.exe"
set "USE_VENV_PY=0"
if exist "%PY_EXE%" set "USE_VENV_PY=1"

if "%USE_VENV_PY%"=="1" (
  if not exist "%PY_EXE%" (
    echo ERROR: no existe el runtime esperado: "%PY_EXE%"
    echo Corre: poetry config virtualenvs.in-project true ^&^& poetry install
    exit /b 1
  )
) else (
  REM Por defecto, NO usamos Poetry para servicios.
  REM Si el servicio corre como LocalSystem, Poetry creará un venv vacío en systemprofile y fallará importando módulos.
  if /i not "%ALLOW_POETRY_FALLBACK%"=="1" (
    echo ERROR: no existe "%PY_EXE%".
    echo Para correr como servicio, crea la venv in-project:
    echo   poetry config virtualenvs.in-project true
    echo   poetry install
    echo Luego vuelve a ejecutar:
    echo   scripts\\nssm_install.bat install
    exit /b 1
  )

  REM Fallback opcional: Poetry (solo si ALLOW_POETRY_FALLBACK=1).
  if not defined POETRY_EXE (
    for %%C in (poetry.exe poetry) do (
      if not defined POETRY_EXE (
        for /f "usebackq delims=" %%I in (`where %%C 2^>nul`) do (
          if not defined POETRY_EXE set "POETRY_EXE=%%I"
        )
      )
    )
  )
  if not defined POETRY_EXE set "POETRY_EXE=poetry"
)

REM Logs
if not exist "%LOG_DIR%" (
  mkdir "%LOG_DIR%" >nul 2>&1
)

echo.
echo NSSM: "%NSSM_EXE%"
echo REPO_DIR: "%REPO_DIR%"
if "%USE_VENV_PY%"=="1" (
  echo Runtime: "%PY_EXE%"
) else (
  echo Runtime: "%POETRY_EXE%" ^(Poetry^)
  echo WARN: se está usando Poetry para servicios ^(ALLOW_POETRY_FALLBACK=1^).
)
echo HOST: %HOST%  PORT: %PORT%
echo LOG_DIR: "%LOG_DIR%"
echo .

if /i "%CMD%"=="uninstall" goto :remove
if /i "%CMD%"=="remove" goto :remove

REM ----------------------
REM API service
REM ----------------------
"%NSSM_EXE%" stop "%SVC_API%" >nul 2>&1
"%NSSM_EXE%" remove "%SVC_API%" confirm >nul 2>&1

if "%USE_VENV_PY%"=="1" (
  "%NSSM_EXE%" install "%SVC_API%" "%PY_EXE%" -m uvicorn print_server.app.main:app --host %HOST% --port %PORT% --access-log --log-level info
) else (
  "%NSSM_EXE%" install "%SVC_API%" "%POETRY_EXE%" run uvicorn print_server.app.main:app --host %HOST% --port %PORT% --access-log --log-level info
)
"%NSSM_EXE%" set "%SVC_API%" AppDirectory "%REPO_DIR%"
"%NSSM_EXE%" set "%SVC_API%" DisplayName "SAVH Print App - API"
"%NSSM_EXE%" set "%SVC_API%" Description "FastAPI (SAVH Print App)"
"%NSSM_EXE%" set "%SVC_API%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SVC_API%" AppStdout "%LOG_DIR%\service_api.out.log"
"%NSSM_EXE%" set "%SVC_API%" AppStderr "%LOG_DIR%\service_api.err.log"
"%NSSM_EXE%" set "%SVC_API%" AppRotateFiles 1
"%NSSM_EXE%" set "%SVC_API%" AppRotateBytes %ROTATE_BYTES%
"%NSSM_EXE%" set "%SVC_API%" AppEnvironmentExtra "PYTHONUNBUFFERED=1"
"%NSSM_EXE%" set "%SVC_API%" AppExit Default Restart
"%NSSM_EXE%" set "%SVC_API%" AppRestartDelay 5000

REM ----------------------
REM Generate worker service
REM ----------------------
"%NSSM_EXE%" stop "%SVC_GEN%" >nul 2>&1
"%NSSM_EXE%" remove "%SVC_GEN%" confirm >nul 2>&1

if "%USE_VENV_PY%"=="1" (
  "%NSSM_EXE%" install "%SVC_GEN%" "%PY_EXE%" -u -m create_prints_server.worker.generate_worker
) else (
  "%NSSM_EXE%" install "%SVC_GEN%" "%POETRY_EXE%" run python -u -m create_prints_server.worker.generate_worker
)
"%NSSM_EXE%" set "%SVC_GEN%" AppDirectory "%REPO_DIR%"
"%NSSM_EXE%" set "%SVC_GEN%" DisplayName "SAVH Print App - Worker (Generate)"
"%NSSM_EXE%" set "%SVC_GEN%" Description "Worker de generacion de PDFs (Google Sheets -> PDFs)"
"%NSSM_EXE%" set "%SVC_GEN%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SVC_GEN%" AppStdout "%LOG_DIR%\service_generate.out.log"
"%NSSM_EXE%" set "%SVC_GEN%" AppStderr "%LOG_DIR%\service_generate.err.log"
"%NSSM_EXE%" set "%SVC_GEN%" AppRotateFiles 1
"%NSSM_EXE%" set "%SVC_GEN%" AppRotateBytes %ROTATE_BYTES%
"%NSSM_EXE%" set "%SVC_GEN%" AppEnvironmentExtra "PYTHONUNBUFFERED=1"
"%NSSM_EXE%" set "%SVC_GEN%" AppExit Default Restart
"%NSSM_EXE%" set "%SVC_GEN%" AppRestartDelay 5000

REM ----------------------
REM Print worker service
REM ----------------------
"%NSSM_EXE%" stop "%SVC_PRINT%" >nul 2>&1
"%NSSM_EXE%" remove "%SVC_PRINT%" confirm >nul 2>&1

if "%USE_VENV_PY%"=="1" (
  "%NSSM_EXE%" install "%SVC_PRINT%" "%PY_EXE%" -u -m print_server.worker.print_worker
) else (
  "%NSSM_EXE%" install "%SVC_PRINT%" "%POETRY_EXE%" run python -u -m print_server.worker.print_worker
)
"%NSSM_EXE%" set "%SVC_PRINT%" AppDirectory "%REPO_DIR%"
"%NSSM_EXE%" set "%SVC_PRINT%" DisplayName "SAVH Print App - Worker (Print)"
"%NSSM_EXE%" set "%SVC_PRINT%" Description "Worker de impresion (SumatraPDF -> impresora)"
"%NSSM_EXE%" set "%SVC_PRINT%" Start SERVICE_AUTO_START
"%NSSM_EXE%" set "%SVC_PRINT%" AppStdout "%LOG_DIR%\service_print.out.log"
"%NSSM_EXE%" set "%SVC_PRINT%" AppStderr "%LOG_DIR%\service_print.err.log"
"%NSSM_EXE%" set "%SVC_PRINT%" AppRotateFiles 1
"%NSSM_EXE%" set "%SVC_PRINT%" AppRotateBytes %ROTATE_BYTES%
"%NSSM_EXE%" set "%SVC_PRINT%" AppEnvironmentExtra "PYTHONUNBUFFERED=1"
"%NSSM_EXE%" set "%SVC_PRINT%" AppExit Default Restart
"%NSSM_EXE%" set "%SVC_PRINT%" AppRestartDelay 5000

echo.
echo Iniciando servicios...
"%NSSM_EXE%" start "%SVC_API%"
"%NSSM_EXE%" start "%SVC_GEN%"
"%NSSM_EXE%" start "%SVC_PRINT%"

echo.
echo OK: servicios instalados e iniciados.
echo Logs:
echo   %LOG_DIR%\service_api.out.log
echo   %LOG_DIR%\service_generate.out.log
echo   %LOG_DIR%\service_print.out.log
echo.
echo Para detener:
echo   "%NSSM_EXE%" stop "%SVC_API%"
echo   "%NSSM_EXE%" stop "%SVC_GEN%"
echo   "%NSSM_EXE%" stop "%SVC_PRINT%"
echo.
echo Para borrar:
echo   "%NSSM_EXE%" remove "%SVC_API%" confirm
echo   "%NSSM_EXE%" remove "%SVC_GEN%" confirm
echo   "%NSSM_EXE%" remove "%SVC_PRINT%" confirm

goto :eof

:remove
echo Removiendo servicios NSSM...
"%NSSM_EXE%" stop "%SVC_PRINT%" >nul 2>&1
"%NSSM_EXE%" stop "%SVC_GEN%" >nul 2>&1
"%NSSM_EXE%" stop "%SVC_API%" >nul 2>&1
"%NSSM_EXE%" remove "%SVC_PRINT%" confirm >nul 2>&1
"%NSSM_EXE%" remove "%SVC_GEN%" confirm >nul 2>&1
"%NSSM_EXE%" remove "%SVC_API%" confirm >nul 2>&1
echo OK: servicios removidos.
goto :eof

:usage
echo Uso:
echo   scripts\\nssm_install.bat install
echo   scripts\\nssm_install.bat uninstall
echo.
echo Overrides (antes de correr):
echo   set NSSM_EXE=C:\\Tools\\nssm\\nssm.exe
echo   set POETRY_EXE=C:\\ruta\\a\\poetry.exe
echo   set HOST=0.0.0.0
echo   set PORT=8000
exit /b 2

endlocal
