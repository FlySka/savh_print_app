Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Wrapper para redirigir a la versión Windows real en scripts/windows/savh.ps1
$windowsScript = Join-Path $PSScriptRoot "windows" | Join-Path -ChildPath "savh.ps1"

if (-not (Test-Path -LiteralPath $windowsScript)) {
  Write-Error "No se encontró scripts/windows/savh.ps1" -ErrorAction Stop
}

# Passthrough de argumentos tal cual llegan
& $windowsScript @Args
