param(
  [Parameter(Position = 0)]
  [ValidateSet("start", "stop", "status", "logs", "help")]
  [string]$Cmd = "help",

  [switch]$Reload,
  [string]$EnvFile = "",
  [string]$LogDir = "data\\logs",
  [string]$PidDir = "data\\pids"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Err([string]$Message) {
  Write-Host $Message -ForegroundColor Red
}

. "$PSScriptRoot/helpers/paths.ps1"
. "$PSScriptRoot/helpers/process.ps1"
. "$PSScriptRoot/helpers/logs.ps1"

$root = Repo-Root
Set-Location -LiteralPath $root

function Resolve-UnderRoot([string]$Path) {
  if (-not $Path) { return $Path }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path $root $Path)
}

# Normaliza paths para que logs/pids queden SIEMPRE en el repo aunque el script se ejecute desde otra carpeta
$LogDir = Resolve-UnderRoot $LogDir $root
$PidDir = Resolve-UnderRoot $PidDir $root
if ($EnvFile) { $EnvFile = Resolve-UnderRoot $EnvFile $root }

if (-not $EnvFile) {
  # Default: .env, pero si existe .env_windows y no hay .env, usa .env_windows para probar rápido.
  if ((Test-Path -LiteralPath ".env")) { $EnvFile = ".env" }
  elseif ((Test-Path -LiteralPath ".env_windows")) { $EnvFile = ".env_windows" }
}

if ($EnvFile) {
  Load-EnvFile $EnvFile
}

Ensure-Dir $LogDir
Ensure-Dir $PidDir

$appPid = Join-Path $PidDir "app.pid"
$genPid = Join-Path $PidDir "generate_worker.pid"
$printPid = Join-Path $PidDir "print_worker.pid"

switch ($Cmd) {
  "start" {
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    # Evita colisión con la variable automática $Host de PowerShell
    $apiHost = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
    $port = if ($env:PORT) { $env:PORT } else { "8000" }
    $reloadFlag = if ($Reload) { "--reload" } else { "" }

    # Un solo log por servicio (stdout+stderr juntos)
    $appLog = Join-Path $LogDir ("app_{0}.log" -f $stamp)
    $genLog = Join-Path $LogDir ("worker_generate_{0}.log" -f $stamp)
    $printLog = Join-Path $LogDir ("worker_print_{0}.log" -f $stamp)

    Write-Host "Iniciando servicios (HOST=$apiHost PORT=$port) env=$EnvFile ..."
    Write-Host "Logs: $LogDir"
    Write-Host "Pids: $PidDir"

    $pyEnvPrefix = "set PYTHONUNBUFFERED=1 &&"
    $apiCmd = "$pyEnvPrefix poetry run uvicorn print_server.app.main:app --host {0} --port {1} --access-log --log-level info {2}" -f $apiHost, $port, $reloadFlag

    Start-One "api" $appPid $appLog $apiCmd $root
    Start-One "generate_worker" $genPid $genLog "$pyEnvPrefix poetry run python -u -m create_prints_server.worker.generate_worker" $root
    Start-One "print_worker" $printPid $printLog "$pyEnvPrefix poetry run python -u -m print_server.worker.print_worker" $root

    Write-Host ""
    Write-Host "Tip: ver logs -> scripts\\savh.ps1 logs"
  }

  "stop" {
    # Evita colisión con la variable automática $Host de PowerShell
    $port = if ($env:PORT) { [int]$env:PORT } else { 8000 }

    Stop-One "print_worker" $printPid
    Stop-One "generate_worker" $genPid
    Stop-One "api" $appPid
    Stop-StrayProcesses
    Stop-ProcessesReferencingLogDir $LogDir
    Stop-ListeningOnPort $port
  }

  "status" {
    Status-One "api" $appPid
    Status-One "generate_worker" $genPid
    Status-One "print_worker" $printPid
  }

  "logs" {
    # Preferimos el formato nuevo (un archivo por servicio): app_YYYYMMDD_HHMMSS.log
    $appLog   = Latest-LogByPattern $LogDir "app_????????_??????.log"
    if (-not $appLog) {
      # Compat: si quedan logs antiguos separados.
      $appLog = Latest-LogByPattern $LogDir "app_*.log"
      if (-not $appLog) { $appLog = Latest-LogByPattern $LogDir "app_*.out.log" }
      if (-not $appLog) { $appLog = Latest-LogByPattern $LogDir "app_*.err.log" }
    }
    $genLog   = Latest-LogByPattern $LogDir "worker_generate_????????_??????.log"
    if (-not $genLog) {
      $genLog = Latest-LogByPattern $LogDir "worker_generate_*.log"
      if (-not $genLog) { $genLog = Latest-LogByPattern $LogDir "worker_generate_*.out.log" }
      if (-not $genLog) { $genLog = Latest-LogByPattern $LogDir "worker_generate_*.err.log" }
    }
    $printLog = Latest-LogByPattern $LogDir "worker_print_????????_??????.log"
    if (-not $printLog) {
      $printLog = Latest-LogByPattern $LogDir "worker_print_*.log"
      if (-not $printLog) { $printLog = Latest-LogByPattern $LogDir "worker_print_*.out.log" }
      if (-not $printLog) { $printLog = Latest-LogByPattern $LogDir "worker_print_*.err.log" }
    }

    $files = @($appLog, $genLog, $printLog) | Where-Object { $_ -ne $null }

    if (-not $files -or $files.Count -eq 0) {
      Write-Host "No hay logs en $LogDir"
      exit 0
    }

    $files = $files | Sort-Object -Property Name

    Write-Host "Mostrando ultimos 200 lines de los logs mas recientes:"
    $files | ForEach-Object { Write-Host "  $($_.Name)" }
    Write-Host ""

    foreach ($f in $files) {
      Write-Host ("==== {0} ====" -f $f.Name)
      Get-Content -LiteralPath $f.FullName -Tail 200 -ErrorAction SilentlyContinue
      Write-Host ""
    }

    Write-Host "Siguiendo (tail -f) los logs:"
    $files | ForEach-Object { Write-Host "  $($_.Name)" }
    Write-Host ""
    try {
      Follow-Logs $files
    } catch {
      Write-Err "WARN: no se pudo seguir múltiples logs; siguiendo solo api."
      if ($appLog) {
        Ensure-File $appLog.FullName
        Get-Content -LiteralPath $appLog.FullName -Tail 0 -Wait
      }
    }
  }

  default {
    Write-Host @"
Uso:
  powershell -ExecutionPolicy Bypass -File scripts\\savh.ps1 start [-reload] [-EnvFile .env]
  powershell -ExecutionPolicy Bypass -File scripts\\savh.ps1 status
  powershell -ExecutionPolicy Bypass -File scripts\\savh.ps1 logs
  powershell -ExecutionPolicy Bypass -File scripts\\savh.ps1 stop

Notas:
  - Logs en $LogDir (con timestamp de inicio).
  - PIDs en $PidDir.
  - Env: por defecto usa .env; si no existe y existe .env_windows, usa .env_windows.
"@
  }
}
