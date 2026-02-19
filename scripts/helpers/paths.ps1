# Helpers de paths y carga de env.

function Repo-Root {
  $scriptsDir = $PSScriptRoot
  if ((Split-Path -Leaf $scriptsDir) -eq "helpers") {
    $scriptsDir = Split-Path -Parent $scriptsDir
  }
  $rootDir = Split-Path -Parent $scriptsDir
  return (Resolve-Path $rootDir).Path
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

function Resolve-UnderRoot([string]$Path, [string]$Root) {
  if (-not $Path) { return $Path }
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return (Join-Path $Root $Path)
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
