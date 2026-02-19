# Helpers de procesos y manejo de pid/log.

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

function Stop-StrayProcesses() {
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
      }
    }
  } catch {
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
    }
  }
}
