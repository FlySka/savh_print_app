Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Err([string]$Message) {
  Write-Host $Message -ForegroundColor Red
}

function Repo-Root {
  $here = Split-Path -Parent $PSScriptRoot
  return (Resolve-Path $here).Path
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Is-RunningPidFile([string]$PidFile) {
  if (-not (Test-Path -LiteralPath $PidFile)) { return $false }
  $pid = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $pid) { return $false }
  try {
    $null = Get-Process -Id ([int]$pid) -ErrorAction Stop
    return $true
  } catch {
    return $false
  }
}

function Stop-One([string]$Name, [string]$PidFile) {
  if (-not (Test-Path -LiteralPath $PidFile)) {
    Write-Host "OK: $Name no tiene pidfile ($PidFile)"
    return
  }
  $pid = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $pid) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "OK: $Name pidfile vacío eliminado"
    return
  }
  try {
    Stop-Process -Id ([int]$pid) -Force -ErrorAction Stop
    Write-Host "OK: $Name detenido pid=$pid"
  } catch {
    Write-Host "OK: $Name no estaba corriendo (pid=$pid)"
  }
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Status-One([string]$Name, [string]$PidFile) {
  if (Is-RunningPidFile $PidFile) {
    $pid = (Get-Content -LiteralPath $PidFile | Select-Object -First 1)
    Write-Host "RUNNING: $Name pid=$pid"
  } else {
    Write-Host "STOPPED: $Name"
  }
}

function Load-EnvFile([string]$EnvFile) {
  if (-not $EnvFile) { return }
  if (-not (Test-Path -LiteralPath $EnvFile)) {
    Write-Err "ERROR: env file no existe: $EnvFile"
    exit 1
  }

  Get-Content -LiteralPath $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line) { return }
    if ($line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $key = $line.Substring(0, $idx).Trim()
    $val = $line.Substring($idx + 1).Trim()

    if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
      $val = $val.Substring(1, $val.Length - 2)
    }

    if ($key) {
      Set-Item -Path "Env:$key" -Value $val
    }
  }
}

function Start-One(
  [string]$Name,
  [string]$PidFile,
  [string]$StdoutLog,
  [string]$StderrLog,
  [string]$CommandLine,
  [string]$WorkingDirectory
) {
  if (Is-RunningPidFile $PidFile) {
    $pid = (Get-Content -LiteralPath $PidFile | Select-Object -First 1)
    Write-Host "OK: $Name ya está corriendo (pid=$pid)"
    return
  }

  # Usamos cmd.exe para ejecutar una command line completa sin pelear con quoting.
  $p = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/c", $CommandLine) `
    -WorkingDirectory $WorkingDirectory `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -PassThru `
    -WindowStyle Hidden

  Set-Content -LiteralPath $PidFile -Value $p.Id -NoNewline
  Write-Host "OK: $Name iniciado pid=$($p.Id)"
  Write-Host "     out=$StdoutLog"
  Write-Host "     err=$StderrLog"
}

function Latest-Logs([string]$LogDir, [int]$Count = 6) {
  if (-not (Test-Path -LiteralPath $LogDir)) { return @() }
  return Get-ChildItem -LiteralPath $LogDir -Filter "*.log" -File |
    Sort-Object -Property LastWriteTime -Descending |
    Select-Object -First $Count
}

param(
  [Parameter(Position = 0)]
  [ValidateSet("start", "stop", "status", "logs", "help")]
  [string]$Cmd = "help",

  [switch]$Reload,
  [string]$EnvFile = "",
  [string]$LogDir = "data\logs",
  [string]$PidDir = "data\pids"
)

$root = Repo-Root
Set-Location -LiteralPath $root

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
    $host = if ($env:HOST) { $env:HOST } else { "127.0.0.1" }
    $port = if ($env:PORT) { $env:PORT } else { "8000" }
    $reloadFlag = if ($Reload) { "--reload" } else { "" }

    $appOut = Join-Path $LogDir ("app_{0}.out.log" -f $stamp)
    $appErr = Join-Path $LogDir ("app_{0}.err.log" -f $stamp)
    $genOut = Join-Path $LogDir ("worker_generate_{0}.out.log" -f $stamp)
    $genErr = Join-Path $LogDir ("worker_generate_{0}.err.log" -f $stamp)
    $printOut = Join-Path $LogDir ("worker_print_{0}.out.log" -f $stamp)
    $printErr = Join-Path $LogDir ("worker_print_{0}.err.log" -f $stamp)

    Write-Host "Iniciando servicios (HOST=$host PORT=$port) env=$EnvFile ..."

    Start-One "api" $appPid $appOut $appErr ("poetry run uvicorn print_server.app.main:app --host {0} --port {1} {2}" -f $host, $port, $reloadFlag) $root
    Start-One "generate_worker" $genPid $genOut $genErr "poetry run python -m create_prints_server.worker.generate_worker" $root
    Start-One "print_worker" $printPid $printOut $printErr "poetry run python -m print_server.worker.print_worker" $root

    Write-Host ""
    Write-Host "Tip: ver logs -> scripts\windows\savh.ps1 logs"
  }

  "stop" {
    Stop-One "print_worker" $printPid
    Stop-One "generate_worker" $genPid
    Stop-One "api" $appPid
  }

  "status" {
    Status-One "api" $appPid
    Status-One "generate_worker" $genPid
    Status-One "print_worker" $printPid
  }

  "logs" {
    $files = Latest-Logs $LogDir 6
    if (-not $files -or $files.Count -eq 0) {
      Write-Host "No hay logs en $LogDir"
      exit 0
    }

    Write-Host "Mostrando últimos 200 lines de:"
    $files | ForEach-Object { Write-Host "  $($_.FullName)" }
    Write-Host ""

    foreach ($f in $files) {
      Write-Host ("==== {0} ====" -f $f.Name)
      Get-Content -LiteralPath $f.FullName -Tail 200 -ErrorAction SilentlyContinue
      Write-Host ""
    }

    Write-Host "Siguiendo el log más reciente: $($files[0].FullName)"
    Get-Content -LiteralPath $files[0].FullName -Wait
  }

  default {
    Write-Host @"
Uso:
  powershell -ExecutionPolicy Bypass -File scripts\windows\savh.ps1 start [-Reload] [-EnvFile .env_windows]
  powershell -ExecutionPolicy Bypass -File scripts\windows\savh.ps1 status
  powershell -ExecutionPolicy Bypass -File scripts\windows\savh.ps1 logs
  powershell -ExecutionPolicy Bypass -File scripts\windows\savh.ps1 stop

Notas:
  - Logs en $LogDir (con timestamp de inicio).
  - PIDs en $PidDir.
  - Env: por defecto usa .env; si no existe y existe .env_windows, usa .env_windows.
"@
  }
}

