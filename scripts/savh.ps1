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

function Repo-Root {
  $here = Split-Path -Parent $PSScriptRoot
  return (Resolve-Path $here).Path
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path | Out-Null
  }
}

function Ensure-File([string]$Path) {
  $dir = Split-Path -Parent $Path
  if ($dir) { Ensure-Dir $dir }
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType File -Path $Path | Out-Null
  }
}

function Is-RunningPidFile([string]$PidFile) {
  if (-not (Test-Path -LiteralPath $PidFile)) { return $false }
  $procId = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $procId) { return $false }
  try {
    $null = Get-Process -Id ([int]$procId) -ErrorAction Stop
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
  $procId = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if (-not $procId) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "OK: $Name pidfile vacío eliminado"
    return
  }

  $pidInt = [int]$procId
  $running = $false
  try {
    $null = Get-Process -Id $pidInt -ErrorAction Stop
    $running = $true
  } catch {
    $running = $false
  }

  if (-not $running) {
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "OK: $Name no estaba corriendo (pid=$pidInt)"
    return
  }

  try {
    # Importante: Stop-Process no mata el árbol. Con uvicorn --reload suelen quedar hijos vivos.
    # taskkill /T mata el árbol completo (cmd.exe -> poetry -> python -> uvicorn/watchfiles).
    $null = (& taskkill.exe /PID $pidInt /T /F 2>$null)
    if ($LASTEXITCODE -eq 0) {
      Write-Host "OK: $Name detenido (taskkill /T) pid=$pidInt"
    } else {
      throw "taskkill exit=$LASTEXITCODE"
    }
  } catch {
    try {
      Stop-Process -Id ([int]$procId) -Force -ErrorAction Stop
      Write-Host "OK: $Name detenido pid=$procId"
    } catch {
      Write-Host "OK: $Name no estaba corriendo (pid=$procId)"
    }
  }
  Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
}

function Status-One([string]$Name, [string]$PidFile) {
  if (Is-RunningPidFile $PidFile) {
    $procId = (Get-Content -LiteralPath $PidFile | Select-Object -First 1)
    Write-Host "RUNNING: $Name pid=$procId"
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
  [string]$LogFile,
  [string]$CommandLine,
  [string]$WorkingDirectory
) {
  if (Is-RunningPidFile $PidFile) {
    $procId = (Get-Content -LiteralPath $PidFile | Select-Object -First 1)
    Write-Host "OK: $Name ya está corriendo (pid=$procId)"
    return
  }

  Ensure-File $LogFile

  # Un solo log por servicio: Uvicorn loggea a stderr por defecto, y Loguru a stdout.
  # Start-Process no permite redirigir stdout+stderr al mismo archivo, asi que lo hacemos en cmd.exe.
  $escapedLog = $LogFile.Replace('"', '""')
  $redirected = "$CommandLine 1>>""$escapedLog"" 2>&1"

  $p = Start-Process -FilePath "cmd.exe" `
    -ArgumentList @("/d", "/s", "/c", $redirected) `
    -WorkingDirectory $WorkingDirectory `
    -PassThru `
    -WindowStyle Hidden

  Set-Content -LiteralPath $PidFile -Value $p.Id -NoNewline
  Start-Sleep -Milliseconds 200
  if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
    Write-Err "ERROR: $Name terminó inmediatamente; revisa el log: $LogFile"
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    return
  }

  Write-Host "OK: $Name iniciado pid=$($p.Id)"
  Write-Host "     log=$LogFile"
}

function Latest-Logs([string]$LogDir, [int]$Count = 6) {
  if (-not (Test-Path -LiteralPath $LogDir)) { return @() }
  return Get-ChildItem -LiteralPath $LogDir -Filter "*.log" -File |
    Sort-Object -Property LastWriteTime -Descending |
    Select-Object -First $Count
}

function Latest-LogByPattern([string]$LogDir, [string]$Pattern) {
  if (-not (Test-Path -LiteralPath $LogDir)) { return $null }
  return Get-ChildItem -LiteralPath $LogDir -Filter $Pattern -File |
    Sort-Object -Property LastWriteTime -Descending |
    Select-Object -First 1
}

function Follow-Logs([System.IO.FileInfo[]]$Files) {
  if (-not $Files -or $Files.Count -eq 0) { return }

  foreach ($f in $Files) {
    Ensure-File $f.FullName
  }

  if ($Files.Count -eq 1) {
    Get-Content -LiteralPath $Files[0].FullName -Tail 0 -Wait
    return
  }

  # Workaround: Get-Content -Wait con múltiples paths es poco confiable (según versión de PowerShell).
  # Creamos un job por archivo y prefijamos cada línea con el nombre del log.
  $jobs = @()
  foreach ($f in $Files) {
    $jobs += Start-Job -Name $f.Name -ArgumentList @($f.FullName, $f.Name) -ScriptBlock {
      param($path, $name)
      Get-Content -LiteralPath $path -Tail 0 -Wait -ErrorAction SilentlyContinue |
        ForEach-Object { "[{0}] {1}" -f $name, $_ }
    }
  }

  try {
    while ($true) {
      foreach ($j in $jobs) {
        # Drena la salida disponible de cada job (si la hay).
        Receive-Job -Job $j -ErrorAction SilentlyContinue
      }
      Start-Sleep -Milliseconds 200
    }
  } finally {
    foreach ($j in $jobs) {
      try { Stop-Job -Job $j -Force -ErrorAction SilentlyContinue } catch {}
      try { Remove-Job -Job $j -Force -ErrorAction SilentlyContinue } catch {}
    }
  }
}

function Stop-StrayProcesses() {
  # En Windows, si el proceso padre muere, a veces quedan hijos vivos (ej: uvicorn --reload).
  # Esto deja logs bloqueados y no permite borrarlos.
  $regexes = @(
    "print_server\\.app\\.main:app",
    "python(\\.exe)?\\s+.*\\s-m\\s+uvicorn\\s+print_server\\.app\\.main:app",
    "uvicorn(\\.exe)?\\s+print_server\\.app\\.main:app",
    "watchfiles",
    "create_prints_server\\.worker\\.generate_worker",
    "python(\\.exe)?\\s+.*\\s-m\\s+create_prints_server\\.worker\\.generate_worker",
    "print_server\\.worker\\.print_worker",
    "python(\\.exe)?\\s+.*\\s-m\\s+print_server\\.worker\\.print_worker"
  )

  foreach ($rx in $regexes) {
    $procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and ($_.CommandLine -match $rx) }
    foreach ($p in $procs) {
      try {
        $null = (& taskkill.exe /PID $p.ProcessId /T /F 2>$null)
        if ($LASTEXITCODE -eq 0) {
          Write-Host "OK: stray detenido (taskkill /T) pid=$($p.ProcessId) match=$rx"
        }
      } catch {
        # Ignora procesos que ya murieron entre el query y el kill.
      }
    }
  }
}

function Stop-ProcessesReferencingLogDir([string]$LogDir) {
  if (-not $LogDir) { return }

  try {
    $escaped = [Regex]::Escape($LogDir)
    $procs = Get-CimInstance Win32_Process | Where-Object {
      $_.CommandLine -and ($_.CommandLine -match $escaped) -and ($_.CommandLine -match "\\.log")
    }
    foreach ($p in $procs) {
      try {
        $null = (& taskkill.exe /PID $p.ProcessId /T /F 2>$null)
        if ($LASTEXITCODE -eq 0) {
          Write-Host "OK: proceso con logs detenido (taskkill /T) pid=$($p.ProcessId)"
        }
      } catch {
        # Ignora procesos que ya murieron.
      }
    }
  } catch {
    # No aborta el stop si fallan consultas CIM.
  }
}

function Stop-ListeningOnPort([int]$Port) {
  if (-not $Port -or $Port -le 0) { return }

  $pids = @()
  try {
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
      $pids = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
    }
  } catch {
    $pids = @()
  }

  if (-not $pids -or $pids.Count -eq 0) {
    try {
      # Fallback clásico: netstat -ano
      $lines = & netstat.exe -ano -p TCP | Select-String -Pattern (":$Port\\s+.*LISTENING\\s+(\\d+)$")
      foreach ($m in $lines.Matches) {
        if ($m.Groups.Count -ge 2) {
          $pids += [int]$m.Groups[1].Value
        }
      }
      $pids = $pids | Sort-Object -Unique
    } catch {
      $pids = @()
    }
  }

  foreach ($pid in $pids) {
    try {
      $null = (& taskkill.exe /PID $pid /T /F 2>$null)
      if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: proceso en puerto $Port detenido (taskkill /T) pid=$pid"
      }
    } catch {
      # Ignora si murió entre el query y el kill.
    }
  }
}

$root = Repo-Root
Set-Location -LiteralPath $root

function Resolve-UnderRoot([string]$Path) {
  if (-not $Path) { return $Path }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path $root $Path)
}

# Normaliza paths para que logs/pids queden SIEMPRE en el repo aunque el script se ejecute desde otra carpeta
$LogDir = Resolve-UnderRoot $LogDir
$PidDir = Resolve-UnderRoot $PidDir
if ($EnvFile) { $EnvFile = Resolve-UnderRoot $EnvFile }

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
