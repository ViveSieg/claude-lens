$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $Root "server.pid"

if (-not (Test-Path -LiteralPath $PidFile)) {
  Write-Output "codex-iris is not running"
  exit 0
}

$pidText = Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue
if (-not $pidText) {
  Remove-Item -LiteralPath $PidFile -Force
  Write-Output "codex-iris pid file was empty"
  exit 0
}

$proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
if ($proc) {
  Stop-Process -Id $proc.Id -Force
  Write-Output "codex-iris stopped (pid $pidText)"
} else {
  Write-Output "codex-iris process not found (pid $pidText)"
}

Remove-Item -LiteralPath $PidFile -Force
