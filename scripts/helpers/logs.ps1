# Helpers de logs (selección y follow).

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
